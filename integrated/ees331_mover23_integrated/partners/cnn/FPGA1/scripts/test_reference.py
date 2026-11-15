"""Software unit tests + an explicitly untrained ONNX integration fixture."""
from pathlib import Path
import copy
import json
import struct
import unittest
import numpy as np
from export_onnx import onnx, helper, numpy_helper, export_model, load_graph, lower, fuse_batchnorm
from reference import convolution, requantize, address
from pack_queue import pack as pack_queue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'build'/'onnx_fixture'


def fixture():
    """7x7 residual bottleneck, GDC7, final FC128. Random weights, NOT trained."""
    rng = np.random.default_rng(1818)
    nodes, initializers = [], []

    def init(name, value):
        initializers.append(numpy_helper.from_array(np.asarray(value, dtype=np.float32), name))
        return name

    lo, hi = init('zero', 0), init('six', 6)

    def conv(name, source, ci, co, k, pad=0, depthwise=False, bn=False, clip=False):
        weight = rng.uniform(-.2, .2, (co, 1 if depthwise else ci, k, k)).astype(np.float32)
        bias = rng.uniform(-.1, .1, co).astype(np.float32)
        out = name+'_out'
        nodes.append(helper.make_node('Conv', [source, init(name+'_w', weight), init(name+'_b', bias)], [out],
                                      name=name, kernel_shape=[k,k], pads=[pad]*4, strides=[1,1], group=ci if depthwise else 1))
        if bn:
            prev, out = out, name+'_bn_out'
            gamma = rng.uniform(.5, 1.5, co); beta = rng.uniform(-.1, .1, co)
            mean = rng.uniform(-.2, .2, co); var = rng.uniform(.4, 1.2, co)
            nodes.append(helper.make_node('BatchNormalization', [prev, init(name+'_gamma', gamma), init(name+'_beta', beta),
                                                                  init(name+'_mean', mean), init(name+'_var', var)], [out], name=name+'_bn', epsilon=1e-4))
        if clip:
            prev, out = out, name+'_clip_out'
            nodes.append(helper.make_node('Clip', [prev, lo, hi], [out], name=name+'_clip'))
        return out

    stem = conv('stem', 'input', 2, 2, 1, bn=True, clip=True)
    expanded = conv('expand', stem, 2, 4, 1, clip=True)
    dw = conv('dw3', expanded, 4, 4, 3, 1, True, True, True)
    projected = conv('project', dw, 4, 2, 1, bn=True)
    nodes.append(helper.make_node('Add', [projected, stem], ['residual_out'], name='residual'))
    # Standalone Clip tests OP_TYPE=RELU6; Identity keeps ADD from being fused.
    nodes.append(helper.make_node('Identity', ['residual_out'], ['identity_out'], name='identity'))
    nodes.append(helper.make_node('Clip', ['identity_out', lo, hi], ['clip_out'], name='standalone_relu6'))
    gdc = conv('gdc7', 'clip_out', 2, 2, 7, depthwise=True, bn=True)
    nodes.append(helper.make_node('Flatten', [gdc], ['flat'], name='flatten', axis=1))
    nodes.append(helper.make_node('Gemm', ['flat', init('fc_w', rng.uniform(-.2,.2,(128,2))),
                                         init('fc_b', np.linspace(-2,2,128))], ['features'], name='fc128', transB=1))
    graph = helper.make_graph(nodes, 'UNTRAINED_operator_fixture',
                              [helper.make_tensor_value_info('input', onnx.TensorProto.FLOAT, [1,2,7,7])],
                              [helper.make_tensor_value_info('features', onnx.TensorProto.FLOAT, [1,128])], initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)], ir_version=8)
    onnx.checker.check_model(model)
    return model


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUT.mkdir(parents=True, exist_ok=True)
        cls.model = fixture()
        cls.model_path = OUT/'untrained_fixture.onnx'
        onnx.save(cls.model, cls.model_path)
        cls.x = np.random.default_rng(55).uniform(-2,2,(1,2,7,7)).astype(np.float32)
        np.save(OUT/'input.npy', cls.x)

    def test_manual_integer_conv_and_depthwise(self):
        x = np.stack([np.arange(1,10).reshape(3,3), -np.arange(1,10).reshape(3,3)]).astype(np.int8)
        dw = convolution(x, np.ones((2,1,3,3), dtype=np.int8), np.array([10,20]), depthwise=True)
        np.testing.assert_array_equal(dw[:,0,0], [55,-25])
        normal = convolution(x, np.ones((1,2,3,3), dtype=np.int8), np.array([7]))
        self.assertEqual(int(normal[0,0,0]), 7)
        np.testing.assert_array_equal(requantize([-257,-256,-3,254,256], 1), [-128,-128,-2,127,127])

    def test_bn_fusion_against_onnx_float_evaluator(self):
        from onnx.reference import ReferenceEvaluator
        rng = np.random.default_rng(3)
        w = rng.normal(0,.3,(3,2,3,3)).astype(np.float32); b = rng.normal(size=3).astype(np.float32)
        gamma = np.array([.5,-2,1.2],dtype=np.float32); beta = rng.normal(size=3).astype(np.float32)
        mean = rng.normal(size=3).astype(np.float32); var = np.array([.1,.5,2],dtype=np.float32)
        fw, fb = fuse_batchnorm(w,b,gamma,beta,mean,var,1e-4)
        init = [numpy_helper.from_array(v,n) for n,v in zip(['w','b','g','be','m','v'],[w,b,gamma,beta,mean,var])]
        nodes = [helper.make_node('Conv',['x','w','b'],['c'],pads=[1]*4),
                 helper.make_node('BatchNormalization',['c','g','be','m','v'],['y'],epsilon=1e-4,training_mode=0)]
        graph = helper.make_graph(nodes,'bn',[helper.make_tensor_value_info('x',onnx.TensorProto.FLOAT,[1,2,7,7])],
                                  [helper.make_tensor_value_info('y',onnx.TensorProto.FLOAT,[1,3,7,7])],init)
        original = helper.make_model(graph,opset_imports=[helper.make_opsetid('',17)],ir_version=8)
        fused = copy.deepcopy(original)
        del fused.graph.node[:]
        fused.graph.node.append(helper.make_node('Conv',['x','fw','fb'],['y'],pads=[1]*4))
        del fused.graph.initializer[:]
        fused.graph.initializer.extend([numpy_helper.from_array(fw.astype(np.float32),'fw'),numpy_helper.from_array(fb.astype(np.float32),'fb')])
        actual = ReferenceEvaluator(original).run(None,{'x':self.x})[0]
        folded = ReferenceEvaluator(fused).run(None,{'x':self.x})[0]
        np.testing.assert_allclose(folded,actual,rtol=2e-5,atol=2e-5)

    def test_full_operator_model_export(self):
        config=export_model(self.model_path,OUT/'export',OUT/'input.npy')
        ops=[x['op'] for x in config['layers']]
        self.assertIn('add',ops)
        self.assertIn('relu6',ops)
        self.assertEqual((OUT/'export/features.golden.bin').stat().st_size,128)
        self.assertEqual(config['queue']['task_count'],len(ops))
        self.assertTrue(all(not x.get('relu6_enable',False) for x in config['layers']))
        # The original skip tensor must survive the entire residual main branch.
        add=next(x for x in config['layers'] if x['op']=='add')
        source=next(x for x in config['layers'] if x['output_addr']==add['weight_addr'])
        self.assertNotEqual(add['output_addr'],source['output_addr'])

    def test_conv_export_and_queue(self):
        weight = np.full((128,3,1,1), .125, dtype=np.float32)
        bias = np.zeros(128, dtype=np.float32)
        graph = helper.make_graph(
            [helper.make_node('Conv', ['x','w','b'], ['features'], name='conv128',
                              kernel_shape=[1,1])],
            'UNTRAINED_conv_only',
            [helper.make_tensor_value_info('x', onnx.TensorProto.FLOAT, [1,3,1,1])],
            [helper.make_tensor_value_info('features', onnx.TensorProto.FLOAT, [1,128,1,1])],
            [numpy_helper.from_array(weight,'w'), numpy_helper.from_array(bias,'b')])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid('',13)], ir_version=8)
        onnx.checker.check_model(model)
        path = OUT/'conv_only.onnx'
        onnx.save(model,path)
        input_path = OUT/'conv_input.npy'
        np.save(input_path,np.array([1.,2.,3.],dtype=np.float32).reshape(1,3,1,1))
        folder = OUT/'conv_export'
        config = export_model(path,folder,input_path)
        self.assertEqual([layer['op'] for layer in config['layers']], ['conv'])
        layer = config['layers'][0]
        self.assertNotIn('control_start',layer)
        np.testing.assert_array_equal(np.fromfile(folder/'features.golden.bin',dtype=np.int8),
                                      np.full(128,12,dtype=np.int8))
        queue = config['queue']
        self.assertEqual(queue['abi_version'],1)
        self.assertEqual(queue['task_count'],1)
        self.assertEqual(queue['control_start'],0x3d)
        self.assertEqual(queue['queue_base'] % 32,0)
        packed = (folder/'queue.bin').read_bytes()
        self.assertEqual(len(packed),32)
        words = struct.unpack('<8I',packed)
        self.assertEqual(words[0],0x100)
        self.assertEqual(words[1],address(layer['input_addr']))
        ram = (folder/'queue_ram.bin').read_bytes()
        self.assertEqual(ram[queue['queue_base']:queue['queue_base']+len(packed)],packed)
        with self.assertRaisesRegex(ValueError,'aligned'):
            pack_queue(folder,base=queue['queue_base']+1)
        with self.assertRaisesRegex(ValueError,'overlaps'):
            pack_queue(folder,base=address(layer['input_addr']) & ~31)

    def test_unsupported_sigmoid_is_error(self):
        model = copy.deepcopy(self.model)
        for node in model.graph.node:
            if node.name=='standalone_relu6':
                node.op_type='Sigmoid'; del node.input[1:]
        path=OUT/'unsupported_sigmoid.onnx';onnx.save(model,path)
        m,s,c=load_graph(path)
        with self.assertRaisesRegex(ValueError,'unsupported Sigmoid'):
            lower(m,s,c)

    def test_residual_scale_conversion(self):
        config=export_model(self.model_path,OUT/'scaled_add',OUT/'input.npy',plan={'project':{'output_frac':3}})
        add=next(x for x in config['layers'] if x['op']=='add')
        self.assertEqual(add['quant_shift'],0)
        memory=(OUT/'scaled_add/ram_init.bin').read_bytes()
        self.assertEqual(struct.unpack_from('<iiIIiI',memory,add['bias_addr']),(2,1,0,0,0,96))

    def test_prelu_pool_export(self):
        nodes=[
            helper.make_node('Conv',['x','w0','b0'],['stem'],name='stem',kernel_shape=[1,1]),
            helper.make_node('PRelu',['stem','slope'],['act'],name='prelu'),
            helper.make_node('MaxPool',['act'],['pooled'],name='pool0',kernel_shape=[2,2],strides=[2,2]),
            helper.make_node('Conv',['pooled','w1','b1'],['projected'],name='project',kernel_shape=[1,1]),
            helper.make_node('Relu',['projected'],['positive'],name='relu'),
            helper.make_node('MaxPool',['positive'],['features'],name='pool1',kernel_shape=[2,2],strides=[2,2])]
        arrays=dict(w0=np.array([1.,-.5]).reshape(2,1,1,1),b0=np.array([-.5,.25]),
                    slope=np.array([.25,.5]).reshape(2,1,1),w1=np.full((128,2,1,1),.125),
                    b1=np.linspace(-1,1,128))
        graph=helper.make_graph(nodes,'UNTRAINED_prelu_pool',
            [helper.make_tensor_value_info('x',onnx.TensorProto.FLOAT,[1,1,4,4])],
            [helper.make_tensor_value_info('features',onnx.TensorProto.FLOAT,[1,128,1,1])],
            [numpy_helper.from_array(np.asarray(v,dtype=np.float32),k) for k,v in arrays.items()])
        model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',13)],ir_version=8)
        onnx.checker.check_model(model)
        onnx.save(model,OUT/'prelu_pool.onnx')
        np.save(OUT/'prelu_pool.npy',np.linspace(-2,2,16,dtype=np.float32).reshape(1,1,4,4))
        config=export_model(OUT/'prelu_pool.onnx',OUT/'prelu_pool_export',OUT/'prelu_pool.npy')
        self.assertEqual([x['op'] for x in config['layers']],['conv','prelu','maxpool','conv','relu','maxpool'])
        self.assertTrue(config['layers'][1]['per_channel'])
        self.assertEqual((OUT/'prelu_pool_export/features.golden.bin').stat().st_size,128)

    def test_asymmetric_padding_is_error(self):
        model=copy.deepcopy(self.model)
        for node in model.graph.node:
            if node.name=='dw3':
                for attr in node.attribute:
                    if attr.name=='pads':
                        attr.ints[:]=[0,1,2,1]
        path=OUT/'asymmetric.onnx';onnx.save(model,path)
        m,s,c=load_graph(path)
        with self.assertRaisesRegex(ValueError,'symmetric'):
            lower(m,s,c)

    def test_relu6_scale_mismatch_is_error(self):
        m,s,c=load_graph(self.model_path)
        with self.assertRaisesRegex(ValueError,'ReLU6 scale'):
            lower(m,s,c,activation_frac=3)


if __name__=='__main__':
    unittest.main(verbosity=2)
