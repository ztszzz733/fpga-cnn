"""Software unit tests + an explicitly untrained ONNX integration fixture."""
from pathlib import Path
import copy
import json
import unittest
import numpy as np
from export_onnx import onnx, helper, numpy_helper, export_model, load_graph, lower, fuse_batchnorm
from reference import convolution, requantize

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

    def test_export_and_residual_liveness(self):
        config = export_model(self.model_path, OUT/'export', OUT/'input.npy')
        self.assertEqual(len(config['layers']), 9)
        self.assertEqual([x['op'] for x in config['layers']],
                         ['conv','conv','depthwise','conv','add','relu6','depthwise','conv','final_output'])
        self.assertGreaterEqual(config['memory_map']['slots'], 3)
        stem, expand, dw, project, add = config['layers'][:5]
        self.assertEqual(add['weight_addr'], stem['output_addr'])
        for x in (expand,dw,project):
            self.assertNotEqual(x['output_addr'], stem['output_addr'])
        self.assertEqual((OUT/'export'/'features.golden.bin').stat().st_size,128)
        self.assertGreater(np.count_nonzero(np.fromfile(OUT/'export'/'features.golden.bin',dtype=np.int8)),100)
        self.assertIn('stem_bn',stem['fused_nodes'])
        self.assertEqual(config['input_clipped_values'],0)

    def test_unsupported_prelu_is_error(self):
        model = copy.deepcopy(self.model)
        for node in model.graph.node:
            if node.name=='standalone_relu6':
                node.op_type='PRelu'; del node.input[1:]; node.input.append('six')
        path=OUT/'unsupported_prelu.onnx';onnx.save(model,path)
        m,s,c=load_graph(path)
        with self.assertRaisesRegex(ValueError,'PReLU'):
            lower(m,s,c)

    def test_residual_scale_mismatch_is_error(self):
        m,s,c=load_graph(self.model_path)
        with self.assertRaisesRegex(ValueError,'identical scale'):
            lower(m,s,c,plan={'project':{'output_frac':3}})

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
