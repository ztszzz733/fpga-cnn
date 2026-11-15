"""Strict ONNX -> CHW, symmetric INT8, shift-only operator tasks.

This is an inference deployment aid, not training or a CPU driver. Unsupported
operators/scales are errors, never silently substituted. Quantization is a
baseline; recognition accuracy must be evaluated with the actual trained model.
"""
from pathlib import Path
import argparse
import json
import math
import re
import sys
import numpy as np

LOCAL_DEPS = Path(__file__).resolve().parents[1] / ('.deps-py39' if sys.version_info < (3,10) else '.deps')
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))
try:
    import onnx
    from onnx import numpy_helper, helper
except ImportError as exc:
    raise SystemExit('Install requirements.txt (ONNX is needed only for export).') from exc
from reference import execute, layer_param, output_shape, task_line, write_memh, write_golden, OPS
from pack_queue import pack as pack_task_queue


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fuse_batchnorm(weight, bias, gamma, beta, mean, variance, epsilon=1e-5):
    """a=gamma/sqrt(var+eps); W'[oc]=a[oc]*W[oc]; b'=beta+a*(b-mean).

    Run in float64 BEFORE weight/bias quantization. Inference statistics only.
    """
    w = np.asarray(weight, dtype=np.float64)
    b, g, be, m, v = [np.asarray(x, dtype=np.float64) for x in (bias, gamma, beta, mean, variance)]
    require(all(x.shape == (w.shape[0],) for x in (b, g, be, m, v)), 'BN channel shape mismatch')
    require(np.all(v + epsilon > 0), 'BN variance + epsilon must be positive')
    a = g / np.sqrt(v + epsilon)
    return w * a.reshape((-1,) + (1,) * (w.ndim - 1)), be + a * (b - m)


def attributes(node):
    return {a.name: helper.get_attribute_value(a) for a in node.attribute}


def chw(shape):
    require(shape is not None and all(isinstance(d, int) and d > 0 for d in shape), f'Dynamic/invalid shape: {shape}')
    require(len(shape) in (2, 4) and shape[0] == 1, f'Expected static N=1 NCHW or [1,C], got {shape}')
    return tuple(shape[1:]) if len(shape) == 4 else (shape[1], 1, 1)


def load_graph(path):
    model = onnx.load(str(path))
    require(all(x.version >= 9 for x in model.opset_import if x.domain in ('', 'ai.onnx')), 'Require ONNX opset >= 9 (inference BatchNorm semantics)')
    onnx.checker.check_model(model)
    model = onnx.shape_inference.infer_shapes(model, strict_mode=True)
    shapes = {}
    for value in list(model.graph.input) + list(model.graph.value_info) + list(model.graph.output):
        dims = value.type.tensor_type.shape.dim
        shapes[value.name] = [d.dim_value if d.HasField('dim_value') else None for d in dims]
    constants = {t.name: numpy_helper.to_array(t) for t in model.graph.initializer}
    for node in model.graph.node:
        if node.op_type == 'Constant':
            a = attributes(node)
            require('value' in a, 'Only tensor Constant nodes are supported')
            constants[node.output[0]] = numpy_helper.to_array(a['value'])
    return model, shapes, constants


def inspect_model(model, shapes, constants):
    report = []
    supported = {'Conv', 'BatchNormalization', 'Relu', 'Clip', 'Add', 'Identity', 'Flatten', 'Reshape', 'Constant', 'Gemm', 'MatMul'}
    for i, node in enumerate(model.graph.node):
        a = attributes(node)
        ins = [shapes.get(x, list(constants[x].shape) if x in constants else None) for x in node.input]
        outs = [shapes.get(x) for x in node.output]
        weight = constants.get(node.input[1]) if len(node.input) > 1 else None
        kernel = a.get('kernel_shape', list(weight.shape[-2:]) if node.op_type == 'Conv' and weight is not None else None)
        group = a.get('group', 1)
        ci = ins[0][1] if ins and ins[0] and len(ins[0]) > 1 else None
        co = outs[0][1] if outs and outs[0] and len(outs[0]) > 1 else None
        report.append(dict(layer_id=i, name=node.name or f'{node.op_type}_{i}', operator_type=node.op_type,
                           input_shape=ins, output_shape=outs, kernel=kernel, stride=a.get('strides'),
                           padding=a.get('pads'), input_channels=ci, output_channels=co, group=group,
                           candidate_supported=node.op_type in supported,
                           note='Requires lowering/shape/scale validation' if node.op_type in supported else 'Unsupported; no silent replacement'))
    return report


def lower(model, shapes, constants, activation_frac=4, input_frac=4, relu6_max=96, plan=None):
    """Lower an acyclic, topologically ordered ONNX graph. Tensor ids retain aliases."""
    require(0 <= activation_frac <= 24 and 0 <= input_frac <= 24, 'Activation fraction must be 0..24')
    plan = plan or {}
    inputs = [x for x in model.graph.input if x.name not in constants]
    require(len(inputs) == 1 and len(model.graph.output) == 1, 'Require exactly one model input and output')
    input_name = inputs[0].name
    require(inputs[0].type.tensor_type.elem_type == onnx.TensorProto.FLOAT, 'Input must be float32; quantize offline')
    require(all(d is not None and d > 0 for d in shapes[input_name]), 'Dynamic input shape is unsupported')
    input_shape = chw(shapes[input_name])
    nodes = list(model.graph.node)
    consumers = {}
    for i, node in enumerate(nodes):
        for name in node.input:
            consumers.setdefault(name, []).append(i)
    for out in model.graph.output:
        consumers.setdefault(out.name, []).append(-1)
    values = {input_name: dict(id=0, shape=input_shape, frac=input_frac)}
    skipped, layers = set(), []

    def constant(name):
        require(name in constants, f'Expected initializer/Constant: {name}')
        x = np.asarray(constants[name], dtype=np.float64)
        require(np.all(np.isfinite(x)), f'Non-finite initializer: {name}')
        return x

    def next_node(name, kind):
        ids = consumers.get(name, [])
        return ids[0] if len(ids) == 1 and ids[0] >= 0 and nodes[ids[0]].op_type in kind else None

    def clip_is_six(node):
        a = attributes(node)
        lo = float(constant(node.input[1]).item()) if len(node.input) > 1 and node.input[1] else a.get('min', -math.inf)
        hi = float(constant(node.input[2]).item()) if len(node.input) > 2 and node.input[2] else a.get('max', math.inf)
        require(lo == 0 and hi == 6, f'{node.name}: only Clip [0,6] is supported')

    for i, node in enumerate(nodes):
        if i in skipped or node.op_type == 'Constant':
            continue
        name = node.name or f'{node.op_type}_{i}'
        a, op = attributes(node), node.op_type
        require(not node.domain or node.domain == 'ai.onnx', f'{name}: custom operator domain unsupported')
        require(node.input and node.input[0] in values, f'{name}: missing data input / unsupported graph ordering')
        v = values[node.input[0]]
        ci, h, w = v['shape']
        require(all(isinstance(x, int) and 0 < x <= 65535 for x in (ci, h, w)), f'{name}: shape exceeds MMIO fields')
        output_name = node.output[0]
        require(len(node.output) == 1, f'{name}: multiple outputs unsupported')
        layer = dict(name=name, op='', width=w, height=h, in_channels=ci, out_channels=ci,
                     kernel=0, stride=0, padding=0, quant_shift=0, relu_enable=False, relu6_enable=False,
                     residual_enable=False, _inputs=[v['id']], input_shape=list(v['shape']), fused_nodes=[])
        q = plan.get(name, {})
        out_frac = int(q.get('output_frac', activation_frac))
        require(0 <= out_frac <= 24, f'{name}: output_frac outside 0..24')
        if op in ('Identity', 'Flatten', 'Reshape'):
            target = chw(shapes[output_name])
            require(int(np.prod(target)) == ci*h*w, f'{name}: reshape changes element count')
            if op == 'Flatten':
                require(a.get('axis', 1) == 1, f'{name}: only Flatten axis=1')
            if op == 'Reshape':
                require(len(node.input) == 2 and node.input[1] in constants, f'{name}: dynamic Reshape unsupported')
            values[output_name] = dict(v, shape=target)
            continue
        if op in ('Conv', 'Gemm', 'MatMul'):
            weight = constant(node.input[1])
            if op == 'Conv':
                require(weight.ndim == 4, f'{name}: Conv weights must be OIHW')
                co, wc, kh, kw = weight.shape
                k = kw
                strides, pads = a.get('strides', [1, 1]), a.get('pads', [0, 0, 0, 0])
                group = a.get('group', 1)
                require(a.get('auto_pad', b'NOTSET') in (b'NOTSET', b'VALID'), f'{name}: auto_pad must be explicit symmetric or VALID')
                if a.get('auto_pad') == b'VALID':
                    pads = [0]*4
                require(kh == kw and a.get('kernel_shape', [kh, kw]) == [kh, kw], f'{name}: non-square/mismatched kernel')
                require(a.get('dilations', [1, 1]) == [1, 1], f'{name}: dilation unsupported')
                require(len(strides) == 2 and strides[0] == strides[1] and 1 <= strides[0] <= 15, f'{name}: stride must be equal in both axes, 1..15')
                require(len(pads) == 4 and len(set(pads)) == 1 and 0 <= pads[0] <= 15, f'{name}: padding must be symmetric, 0..15')
                if group == 1 and k in (1, 3) and wc == ci:
                    layer['op'] = 'conv'
                elif group == ci == co and wc == 1 and k in (3, 7):
                    layer['op'] = 'depthwise'
                else:
                    raise ValueError(f'{name}: unsupported kernel/group/channel multiplier ({k}, {group}, {ci}->{co})')
                bias = constant(node.input[2]) if len(node.input) > 2 else np.zeros(co)
                layer.update(kernel=k, stride=strides[0], padding=pads[0])
            else:
                require(h == w == 1 and len(shapes[node.input[0]]) == 2, f'{name}: linear input must be [1,C]')
                require(weight.ndim == 2 and not a.get('transA', 0), f'{name}: unsupported matrix layout')
                # Gemm Y=alpha*A*B+beta*C; normal 1x1 expects [OC,IC,1,1].
                if op == 'MatMul' or not a.get('transB', 0):
                    weight = weight.T
                weight = weight * a.get('alpha', 1.0)
                co, wc = weight.shape
                require(wc == ci, f'{name}: linear input channels mismatch')
                weight = weight.reshape(co, ci, 1, 1)
                bias = constant(node.input[2]) * a.get('beta', 1.0) if len(node.input) > 2 else np.zeros(co)
                if bias.size == co:
                    bias = bias.reshape(co)
                layer.update(op='conv', kernel=1, stride=1)
            require(bias.shape == (co,) and 0 < co <= 65535, f'{name}: bias/output channels mismatch')
            layer['out_channels'] = co
            bn_idx = next_node(output_name, {'BatchNormalization'})
            if bn_idx is not None:
                bn = nodes[bn_idx]; ba = attributes(bn)
                require(not ba.get('training_mode', 0) and len(bn.output) == 1, f'{name}: training BatchNorm unsupported')
                weight, bias = fuse_batchnorm(weight, bias, *(constant(x) for x in bn.input[1:5]), ba.get('epsilon', 1e-5))
                skipped.add(bn_idx); output_name = bn.output[0]
                layer['fused_nodes'].append(bn.name or f'BatchNormalization_{bn_idx}')
            max_abs = float(np.max(np.abs(weight)))
            wf = int(q.get('weight_frac', min(24, math.floor(math.log2(127/max_abs))) if max_abs else 7))
            require(-24 <= wf <= 24, f'{name}: weight scale outside supported export range')
            wq = np.rint(weight * (2.0**wf))
            require(np.all((wq >= -128) & (wq <= 127)), f'{name}: chosen weight_frac clips weights')
            bq = np.rint(bias * (2.0**(v['frac']+wf)))
            require(np.all(np.isfinite(bq)) and np.all((bq >= -(2**31)) & (bq <= 2**31-1)), f'{name}: bias INT32 overflow')
            layer.update(_weight=wq.astype(np.int8), _bias=bq.astype('<i4'), weight_frac=wf,
                         quant_shift=v['frac']+wf-out_frac)
        elif op == 'Add':
            require(len(node.input) == 2 and node.input[1] in values, f'{name}: Add requires two feature tensors')
            b = values[node.input[1]]
            require(b['shape'] == v['shape'], f'{name}: Add broadcasting is unsupported')
            layer.update(op='add', quant_shift=max(0,v['frac']-out_frac), _inputs=[v['id'], b['id']])
            if b['frac']!=v['frac'] or out_frac>v['frac']:
                def scale_pair(frac):
                    delta=out_frac-frac
                    return (1<<delta,0) if delta>=0 else (1,-delta)
                ma,sa=scale_pair(v['frac']);mb,sb=scale_pair(b['frac'])
                layer.update(quant_shift=0,_params=[[ma,mb,sa,sb,0,96]])
        elif op == 'Clip':
            clip_is_six(node)
            layer.update(op='relu6', quant_shift=v['frac']-out_frac)
        elif op=='Relu':
            layer.update(op='relu',quant_shift=v['frac']-out_frac)
        elif op=='PRelu':
            slope=constant(node.input[1])
            require(slope.size==1 or slope.shape in ((ci,1,1),(1,ci,1,1)), f'{name}: unsupported PReLU broadcasting')
            require(out_frac==v['frac'],f'{name}: PReLU keeps the activation scale')
            slopes=np.broadcast_to(slope.reshape(-1),(ci,))
            records=[]
            for alpha in slopes:
                require(abs(alpha)<32768,f'{name}: PReLU slope too large')
                records.append([int(np.rint(alpha*65536)),1,16,0,0,96])
            layer.update(op='prelu',per_channel=True,_params=records)
        elif op=='MaxPool':
            require(a.get('kernel_shape')==[2,2] and a.get('strides',[1,1])==[2,2] and
                    a.get('pads',[0,0,0,0])==[0,0,0,0] and not a.get('ceil_mode',0) and
                    a.get('dilations',[1,1])==[1,1] and a.get('auto_pad',b'NOTSET') in (b'NOTSET',b'VALID'),
                    f'{name}: MaxPool requires 2x2 stride2, no padding, floor')
            layer.update(op='maxpool',kernel=2,stride=2,quant_shift=v['frac']-out_frac)
        else:
            raise ValueError(f'{name}: unsupported {op}')
        # Activations are explicit tasks, independently scheduled by the hardware.
        require(0 <= layer['quant_shift'] <= 255, f'{name}: scale requires unsupported left shift; adjust quant plan')
        if layer['relu6_enable'] or layer['op']=='relu6':
            require(6*(2**out_frac) == relu6_max and 0 < relu6_max <= 127, f'{name}: ReLU6 scale must match RTL RELU6_MAX={relu6_max}')
        target = chw(shapes[output_name])
        require(target == output_shape(layer) and all(x > 0 for x in target), f'{name}: inferred shape differs from hardware geometry')
        layer.update(output_shape=list(target), input_frac=v['frac'], output_frac=out_frac,
                     layer_id=len(layers), _output=len(layers)+1, output_tensor=output_name)
        layers.append(layer)
        values[output_name] = dict(id=layer['_output'], shape=target, frac=out_frac)
    final_name = model.graph.output[0].name
    require(final_name in values, 'Unresolved model output')
    final = values[final_name]
    require(final['shape'] == (128, 1, 1), f"Final output must contain 128 features, got {final['shape']}")
    layers.append(dict(name='FINAL_OUTPUT', op='final_output', layer_id=len(layers), width=1, height=1,
                       in_channels=128, out_channels=128, _inputs=[final['id']], _output=len(layers)+1,
                       input_shape=[128,1,1], output_shape=[128,1,1], input_frac=final['frac'], output_frac=final['frac']))
    unused = set(plan) - {x['name'] for x in layers}
    require(not unused, f'Quant plan has unknown/fused layer names: {sorted(unused)}')
    return input_name, input_shape, layers


def allocate(layers, input_size, base=0x1000):
    """Liveness-based equal slots: ping-pong for a chain; keep skips until last use.

    Allocate destination before freeing source, because RTL forbids in-place writes.
    """
    capacity = (max([input_size] + [int(np.prod(x['output_shape'])) for x in layers]) + 255) & ~255
    uses = {}
    for x in layers:
        for src in x['_inputs']:
            uses[src] = uses.get(src, 0) + 1
    slots, free, next_slot = {0: 0}, [], 1
    for x in layers:
        dst = min(free) if free else next_slot
        if free:
            free.remove(dst)
        else:
            next_slot += 1
        slots[x['_output']] = dst
        x['input_addr'] = base + slots[x['_inputs'][0]]*capacity
        x['output_addr'] = base + dst*capacity
        if x['op'] == 'add':
            x['weight_addr'] = base + slots[x['_inputs'][1]]*capacity
        x['feature_slot'] = dst
        for src in x['_inputs']:
            uses[src] -= 1
            if uses[src] == 0:
                free.append(slots[src])
    return dict(base=base, slot_bytes=capacity, slots=next_slot, end=base+next_slot*capacity)


def export_model(model_path, out_dir, input_npy=None, activation_frac=4, input_frac=4, relu6_max=96, plan=None):
    model, shapes, constants = load_graph(model_path)
    report = inspect_model(model, shapes, constants)
    name, shape, layers = lower(model, shapes, constants, activation_frac, input_frac, relu6_max, plan)
    # Flatten/reshape aliases need no hardware task or copy.
    if layers and layers[-1]['op']=='final_output':
        require(len(layers)>1 and layers[-1]['_inputs']==[layers[-2]['_output']],
                'Final tensor must come from the last scheduled operator')
        layers=layers[:-1]
    require(layers and all(x['op'] in ('conv','depthwise','relu','relu6','add','prelu','maxpool') for x in layers),
            'Unsupported hardware operator')
    out = Path(out_dir).resolve()
    require(not any(c.isspace() for c in str(out)), 'Testbench task paths cannot contain spaces; choose another export directory')
    out.mkdir(parents=True, exist_ok=True)
    memory_map = allocate(layers, int(np.prod(shape)))
    weight_base = (memory_map['end'] + 255) & ~255
    weights, biases = bytearray(), bytearray()
    for x in layers:
        if '_weight' in x:
            x['weight_addr'] = weight_base + len(weights)
            x['weight_offset'] = len(weights)
            weights.extend(x['_weight'].tobytes())
    bias_base = (weight_base + len(weights) + 3) & ~3
    for x in layers:
        if '_bias' in x:
            x['bias_addr'] = bias_base + len(biases)
            x['bias_offset'] = len(biases)
            biases.extend(x['_bias'].tobytes())
        elif '_params' in x:
            import struct
            x['bias_addr']=bias_base+len(biases)
            x['bias_offset']=len(biases)
            biases.extend(b''.join(struct.pack('<iiIIiI',*record) for record in x['_params']))
    needed = bias_base + len(biases) + 256
    require(needed <= 2**32, 'RAM address map exceeds 32 bits')
    # Generic TB also exercises error/reset cases at fixed addresses below 0x30010.
    ram_bytes = max(262144, 1 << (needed-1).bit_length())
    if input_npy is None:
        xq = np.zeros(shape, dtype=np.int8)
        input_source, clipped = 'zeros_smoke_only', 0
    else:
        xin = np.load(input_npy, allow_pickle=False)
        if xin.shape == (1, *shape):
            xin = xin[0]
        require(xin.shape == shape, f'Input .npy shape {xin.shape}, expected CHW {shape}')
        require(np.issubdtype(xin.dtype, np.floating), 'Input .npy must contain preprocessed float activations, not raw INT8')
        require(np.all(np.isfinite(xin)), 'Non-finite input')
        scaled = np.rint(xin.astype(np.float64) * 2**input_frac)
        clipped = int(np.sum((scaled < -128) | (scaled > 127)))
        xq = np.clip(scaled, -128, 127).astype(np.int8)
        input_source = str(Path(input_npy).resolve())
    segments = [(memory_map['base'], xq.tobytes()), (weight_base, weights), (bias_base, biases)]
    initial = bytearray([0xa5])*ram_bytes
    for addr, data in segments:
        initial[addr:addr+len(data)] = data
    (out/'weight.bin').write_bytes(weights); (out/'bias.bin').write_bytes(biases)
    (out/'input.bin').write_bytes(xq.tobytes()); (out/'ram_init.bin').write_bytes(initial)
    write_memh(out/'ram_init.hex', [(a,d) for a,d in segments if d])
    memory = initial.copy()
    tasks, public = [], []
    for i, layer in enumerate(layers):
        y = execute(memory, layer, relu6_max)
        golden = out/f'layer_{i:03d}.golden.hex'
        write_golden(golden, y)
        task_name = re.sub(r'[^A-Za-z0-9_-]', '_', layer['name'])
        tasks.append(task_line((out/'ram_init.hex').as_posix() if i == 0 else '-', f'{i}_{task_name}', layer, golden.as_posix()))
        entry = {k:v for k,v in layer.items() if not k.startswith('_')}
        entry.update(descriptor_header=0x100 | OPS[layer['op']], feature_size=(layer['height']<<16)|layer['width'],
                     channels=(layer['out_channels']<<16)|layer['in_channels'], layer_param=layer_param(layer))
        public.append(entry)
    config = dict(format_version=1, layout='CHW', weight_layout='OIHW / C1KK', byte_order='little', dtype='int8',
                  model=str(Path(model_path).resolve()), input_name=name, input_shape=list(shape), input_source=input_source,
                  input_clipped_values=clipped, input_frac=input_frac, relu6_max=relu6_max, ram_bytes=ram_bytes,
                  memory_map=memory_map, weight_base=weight_base, bias_base=bias_base,
                  final_output_addr=layers[-1]['output_addr'], final_features=128, layers=public,
                  quantization='symmetric zero-point 0, power-of-two scales; int32 wrap; arithmetic shift; saturate int8',
                  accuracy_note='Integer reference equivalence is not recognition accuracy; calibrate/validate the actual model.')
    (out/'layer_config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    (out/'model_layers.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (out/'tasks.txt').write_text(str(len(tasks))+'\n'+'\n'.join(tasks)+'\n', encoding='ascii')
    (out/'features.golden.bin').write_bytes(y.tobytes())
    config['queue']=pack_task_queue(out)
    (out/'layer_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    return config


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('model'); p.add_argument('--out', default='build/export')
    p.add_argument('--inspect-only', action='store_true'); p.add_argument('--input-npy')
    p.add_argument('--activation-frac', type=int, default=4); p.add_argument('--input-frac', type=int, default=4)
    p.add_argument('--relu6-max', type=int, default=96); p.add_argument('--quant-plan', help='JSON: layer name -> {weight_frac, output_frac}')
    args = p.parse_args()
    try:
        model, shapes, constants = load_graph(args.model)
        report = inspect_model(model, shapes, constants)
        for x in report:
            print(f"{x['layer_id']:3} {x['name']} {x['operator_type']} {x['input_shape']} -> {x['output_shape']} "
                  f"K={x['kernel']} S={x['stride']} P={x['padding']} CI={x['input_channels']} CO={x['output_channels']}")
        if args.inspect_only:
            out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
            (out/'model_layers.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            return
        plan = json.loads(Path(args.quant_plan).read_text()) if args.quant_plan else None
        config = export_model(args.model, args.out, args.input_npy, args.activation_frac, args.input_frac, args.relu6_max, plan)
        print(f"Exported {len(config['layers'])} tasks, {config['memory_map']['slots']} feature slots, RAM {config['ram_bytes']} bytes")
        print('Run RTL: python scripts/run_tests.py mobilefacenet --tasks '+str(Path(args.out)/'tasks.txt')+f" --ram-bytes {config['ram_bytes']}")
        print('Run queue: python scripts/run_tests.py task_queue --queue-dir '+str(Path(args.out))+f" --ram-bytes {config['queue']['ram_bytes']}")
        if not args.input_npy:
            print('Input is all zeros: smoke test only. Supply --input-npy for model input validation.')
    except (ValueError, onnx.checker.ValidationError, onnx.shape_inference.InferenceError) as exc:
        p.exit(2, f'EXPORT ERROR: {exc}\n')


if __name__ == '__main__':
    main()
