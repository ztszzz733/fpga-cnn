"""Check deployment descriptors cannot silently request removed operators."""
import struct
import unittest
from pack_queue import descriptor


class ArrayProfile(unittest.TestCase):
    def layer(self):
        return dict(op='conv',input_addr=0x101,output_addr=0x401,weight_addr=0x201,bias_addr=0x300,
                    width=2,height=1,in_channels=3,out_channels=2,kernel=1,stride=1,padding=0,quant_shift=0)

    def test_abi(self):
        self.assertEqual(struct.unpack('<8I',descriptor(self.layer())),(0x100,0x101,0x401,0x201,0x300,0x10002,0x20003,0x11))

    def test_removed_ops(self):
        for op in ('copy','final_output','sigmoid'):
            layer=self.layer();layer['op']=op
            with self.subTest(op=op),self.assertRaises(ValueError):descriptor(layer)

    def test_scalar_descriptors(self):
        for op,code in [('relu6',2),('add',3),('relu',6),('prelu',7),('maxpool',8),('requant',10)]:
            x=self.layer();x.update(op=op,in_channels=2,kernel=2 if op=='maxpool' else 0,stride=2 if op=='maxpool' else 0)
            self.assertEqual(struct.unpack('<8I',descriptor(x))[0],0x100|code)

    def test_activation_flags(self):
        for flag in ('relu_enable','relu6_enable','residual_enable'):
            layer=self.layer();layer[flag]=True
            with self.subTest(flag=flag),self.assertRaises(ValueError):descriptor(layer)

    def test_depthwise(self):
        layer=self.layer();layer.update(op='depthwise',kernel=7,in_channels=2)
        self.assertEqual(struct.unpack('<8I',descriptor(layer))[0],0x101)


if __name__=='__main__':unittest.main()
