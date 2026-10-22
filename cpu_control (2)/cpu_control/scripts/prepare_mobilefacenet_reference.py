"""Pinned TorchScript -> ONNX -> local image reference and operator inventory.

Run with the Windows bundled Python. Dependencies live in .tools, not globally.
No face labels/identities or accuracy claims are inferred from input filenames.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'.tools/mobilefacenet-python'))
import numpy as np
from PIL import Image
import torch
import onnx
from onnx import numpy_helper
import onnxruntime as ort


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preprocessing(image):
    # Reproduce pinned upstream data_gen.py val transform (no random augment).
    x = np.asarray(image.convert('RGB'), dtype=np.float32)/255.0
    return ((x-np.array([.485,.456,.406], np.float32))/np.array([.229,.224,.225], np.float32)).transpose(2,0,1)[None].copy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--pattern', default='person_*.jpg')
    args = parser.parse_args()
    files = sorted(args.images.glob(args.pattern))
    if not files:
        raise RuntimeError('No input images matched')
    out = ROOT/'build/runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_mobilefacenet_reference')
    out.mkdir(parents=True)
    print('RUN_DIR='+str(out), flush=True)
    start = time.perf_counter()
    upstream = ROOT/'.tools/mobilefacenet-upstream'
    checkpoint = upstream/'pretrained_model/mobilefacenet_scripted.pt'
    commit = subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'], text=True).strip()
    torch.set_num_threads(2)
    model = torch.jit.load(str(checkpoint), map_location='cpu').eval()
    (out/'torchscript_graph.txt').write_text(str(model.inlined_graph), encoding='utf-8')
    onnx_path = out/'mobilefacenet.onnx'
    dummy = torch.zeros(1,3,112,112)
    with torch.inference_mode():
        expected = model(dummy)
        torch.onnx.export(model, dummy, str(onnx_path), opset_version=17,
                          input_names=['image'], output_names=['embedding'],
                          do_constant_folding=True, dynamo=False)
    graph = onnx.shape_inference.infer_shapes(onnx.load(onnx_path))
    onnx.checker.check_model(graph)
    onnx.save(graph, onnx_path)
    shapes = {v.name:[d.dim_value for d in v.type.tensor_type.shape.dim]
              for v in [*graph.graph.input,*graph.graph.value_info,*graph.graph.output]}
    tensors = {t.name:numpy_helper.to_array(t) for t in graph.graph.initializer}
    constants = dict(tensors)
    for node in graph.graph.node:
        if node.op_type == 'Constant':
            value = next((a.t for a in node.attribute if a.name=='value'), None)
            if value is not None:
                constants[node.output[0]] = numpy_helper.to_array(value)
    inventory = []
    for i, node in enumerate(graph.graph.node):
        attrs = {a.name:onnx.helper.get_attribute_value(a) for a in node.attribute}
        shape = shapes.get(node.output[0], [])
        row = dict(index=i, name=node.name, op=node.op_type, output_shape=shape, inputs=list(node.input), output=node.output[0])
        if node.op_type == 'Conv':
            weight = tensors[node.input[1]]
            kernel = list(weight.shape[2:])
            group = int(attrs.get('group',1))
            row.update(kernel=kernel, group=group, strides=attrs.get('strides',[1,1]), pads=attrs.get('pads',[0,0,0,0]),
                       weight_shape=list(weight.shape), macs=math.prod(shape)*math.prod(weight.shape[1:]))
            row['mapping'] = ('NEureka 1x1; channel tiling/padding/quantization pending' if kernel==[1,1] else
                              'NEureka DW3x3; padding/stride/channel tiling pending' if kernel==[3,3] and group>1 else
                              'NEureka dense3x3; padding/stride/quantization pending' if kernel==[3,3] else
                              'GDConv7x7: partition into 3x3/edge terms with wide accumulation; NOT implemented' if kernel==[7,7] and group>1 else 'Unmapped')
        else:
            if node.op_type == 'Clip':
                row['clip_range'] = [float(constants[node.input[1]]),float(constants[node.input[2]])]
                assert row['clip_range'] == [0.0,6.0], 'Unexpected activation: revise operator mapping'
            row['mapping'] = {'Relu':'Existing post ReLU; model-scale integration pending',
                              'Clip':'Clamp/ReLU6; new quantized upper-bound path needed',
                              'PRelu':'Per-channel slope kernel needed',
                              'Add':'Residual add with scale alignment needed',
                              'BatchNormalization':'Fold into preceding convolution offline',
                              'Reshape':'Metadata/layout handling', 'Flatten':'Metadata/layout handling',
                              'Constant':'Compile-time constant', 'Identity':'Alias/no arithmetic'}.get(node.op_type,'Review required')
        inventory.append(row)
    (out/'operators.json').write_text(json.dumps(inventory, indent=2))
    with (out/'operators.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['index','name','op','output_shape','kernel','group','strides','pads','weight_shape','macs','mapping'], extrasaction='ignore')
        writer.writeheader(); writer.writerows(inventory)
    opts = ort.SessionOptions(); opts.intra_op_num_threads=2; opts.inter_op_num_threads=1
    session = ort.InferenceSession(str(onnx_path), opts, providers=['CPUExecutionProvider'])
    rows, vectors, inputs = [], [], []
    for path in files:
        image = Image.open(path)
        if image.size != (112,112):
            raise ValueError(f'{path}: expected pre-cropped 112x112 input, got {image.size}')
        x = preprocessing(image); inputs.append(x)
        stamp=time.perf_counter()
        with torch.inference_mode():
            y=model(torch.from_numpy(x)).numpy()
        oy=session.run(None, {'image':x})[0]
        np.testing.assert_allclose(oy,y,rtol=2e-4,atol=2e-5)
        assert y.shape == (1,128) and np.isfinite(y).all()
        norm=float(np.linalg.norm(y))
        assert norm>0
        vectors.append(y[0]/norm)
        rows.append(dict(file=str(path), sha256=sha(path), output_shape=list(y.shape), raw_l2_norm=norm,
                         torch_onnx_max_abs_error=float(np.max(np.abs(y-oy))), seconds=time.perf_counter()-stamp))
    vectors=np.stack(vectors); similarity=vectors@vectors.T
    np.testing.assert_allclose(np.diag(similarity),1,atol=1e-6)
    np.save(out/'normalized_embeddings.npy',vectors)
    with (out/'cosine_similarity.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['image']+[p.name for p in files])
        for path,row in zip(files,similarity):writer.writerow([path.name]+[f'{float(v):.8f}' for v in row])
    # Observe every arithmetic activation. Four samples only: diagnostic ranges,
    # NOT a production calibration set or evidence of INT8 recognition accuracy.
    range_graph=onnx.ModelProto();range_graph.CopyFrom(graph)
    value_info={v.name:v for v in [*graph.graph.value_info,*graph.graph.output]}
    del range_graph.graph.output[:]
    selected=[r for r in inventory if r['op'] in ('Conv','Relu','PRelu','Clip','Add','BatchNormalization')]
    for row in selected:range_graph.graph.output.append(value_info[row['output']])
    rangesession=ort.InferenceSession(range_graph.SerializeToString(),opts,providers=['CPUExecutionProvider'])
    ranges=[dict(node=r['name'],op=r['op'],min=float('inf'),max=-float('inf')) for r in selected]
    gd = next((r for r in selected if r.get('kernel')==[7,7] and r.get('group',1)>1), None)
    lowering = []
    for image_index,x in enumerate(inputs):
        values = rangesession.run(None,{'image':x})
        observed = {r['output']:v for r,v in zip(selected,values)}
        for r,output in zip(ranges,values):
            r['min']=min(r['min'],float(output.min()));r['max']=max(r['max'],float(output.max()))
        if gd:
            a = observed[gd['inputs'][0]][0]
            w = tensors[gd['inputs'][1]][:,0]
            assert a.shape == w.shape and a.shape[1:]==(7,7)
            # This is a CPU integer lowering proof, NOT execution on NEureka.
            sx = max(float(np.max(np.abs(a)))/127,1e-12)
            sw = np.maximum(np.max(np.abs(w),axis=(1,2))/127,1e-12)
            qa = np.clip(np.rint(a/sx),-127,127).astype(np.int64)
            qw = np.clip(np.rint(w/sw[:,None,None]),-127,127).astype(np.int64)
            direct = (qa*qw).sum(axis=(1,2))
            # 7x7 -> nine <=3x3 patches; signed input represented as unsigned
            # with exact weight-sum correction. Accumulate before quantizing.
            parts = []
            for y in range(0,7,3):
                for z in range(0,7,3):
                    aw = qa[:,y:y+3,z:z+3]+128
                    ww = qw[:,y:y+3,z:z+3]
                    parts.append((aw*ww).sum(axis=(1,2))-128*ww.sum(axis=(1,2)))
            lowered = np.stack(parts).sum(axis=0)
            np.testing.assert_array_equal(lowered,direct)
            assert np.max(np.abs(lowered)) < 2**31
            fp = (a*w).sum(axis=(1,2))
            reconstructed = direct*sx*sw
            lowering.append(dict(image=files[image_index].name,channels=len(direct),patches=9,
                                 exact_integer_match=True,max_abs_accumulator=int(np.max(np.abs(direct))),
                                 local_quantization_max_abs_error=float(np.max(np.abs(fp-reconstructed))),
                                 local_quantization_rmse=float(np.sqrt(np.mean((fp-reconstructed)**2))),
                                 note='Bias/BN excluded from this local dot-product comparison; no network INT8 accuracy claim'))
    for r in ranges:
        r['observed_symmetric_int8_scale']=max(abs(r['min']),abs(r['max']))/127
        r['contains_negative']=r['min']<0
    (out/'activation_ranges.json').write_text(json.dumps(ranges,indent=2))
    (out/'gdconv_lowering.json').write_text(json.dumps(dict(hardware_implemented=False,cases=lowering),indent=2))
    record=dict(status='PASS',checkpoint=str(checkpoint),checkpoint_sha256=sha(checkpoint),upstream_commit=commit,
                preparation_script_sha256=sha(Path(__file__)),
                source='https://github.com/foamliu/MobileFaceNet',onnx_sha256=sha(onnx_path),
                versions=dict(torch=torch.__version__,onnx=onnx.__version__,onnxruntime=ort.__version__,numpy=np.__version__),
                input_shape=[1,3,112,112],output_shape=list(expected.shape),
                parameters=sum(p.numel() for p in model.parameters()),
                op_counts=dict(collections.Counter(r['op'] for r in inventory)),
                convolution_macs=sum(r.get('macs',0) for r in inventory),images=rows,
                preprocessing=dict(layout='NCHW',color='RGB',mean=[.485,.456,.406],std=[.229,.224,.225],range_before_normalization=[0,1],
                                   source='pinned upstream data_gen.py val; demo.py uses a different convention',horizontal_flip=False),
                alignment='Input files already 112x112; landmark alignment not established or performed',
                accuracy_evaluated=False,full_network_rtl=False,quantized_network=False,
                total_seconds=time.perf_counter()-start)
    (out/'result.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2),flush=True)


if __name__=='__main__':
    main()
