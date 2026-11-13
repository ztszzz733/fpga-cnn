# 任务队列、共享脉动阵列与多算子加速器

当前实现位于 FPGA1 根目录。加速器只接受 RAM 任务队列，提供 4 个有效 MMIO 控制／状态寄存器、5 个保留地址槽位，以及简单的 32 bit RAM master 接口。RAM 可以位于 CPU 子系统内部，由系统侧连接和共享。

- Conv 1×1/3×3、Depthwise 3×3/7×7、MatMul共用一套8×8脉动阵列，保留两个PE分区上下文。
- ReLU、ReLU6、PReLU、Residual ADD、2×2 MaxPool、增强Requant各有独立执行单元。
- 最多8条任务在途；空闲单元可接收窗口内较晚的独立任务。RAW/WAR/WAW同时检查在途任务和更早待执行任务。
- 输入/权重INT8，阵列累加INT32；默认输出INT8，也可输出原始INT32后接独立量化。
- RAM访问共享仲裁，busy重叠不等于所有单元每拍都在计算。

## 运行

在 FPGA1 目录执行：

```powershell
python scripts/verify_all.py
python scripts/operator_wave.py --open
```

完整ONNX导出测试（本机已有.deps对应Python3.11）：

```powershell
py -3.11 scripts/verify_all.py --onnx
```

多算子波形、逐行解释和任务实际时间表位于 build/operator_vectors/。
旧的阵列教学入口仍可用：python scripts/systolic_wave.py --open。
修改 examples/systolic_wave.json 可改变该教学示例输入。

## 入口

- [CPU 内部 RAM 对接与代码交付说明](docs/cpu_internal_ram_integration.md)
- [当前架构、算子、任务格式、数值规则及限制](docs/heterogeneous_ops.md)
- [文档索引](docs/README.md)
- RTL：rtl/；生产编译清单：rtl/files.f；顶层：mobilefacenet_accelerator_top。
- 测试：tb/；tb/support/只用于独立阵列测试，不参与顶层综合。
- 软件参考、ONNX转换、任务打包与仿真入口：scripts/。
- 结果：build/verification.json、build/operator_vectors/result.json、各测试日志和逐字节comparison.csv。
- 改动前工作区备份：build/checkpoints/before_heterogeneous_ops.zip。
- 先前整理保留的输入和备份：build/retained_data/。
- 手工修改的图和draw_compute_engine.py原样保留；它们描绘旧结构，当前结构见新文档。

需要Python3.9+、NumPy、Icarus Verilog；结构检查需要Yosys；波形查看需要GTKWave；ONNX转换另需requirements.txt的依赖。
不包含CPU、SoC、人脸检测、训练或身份比较。尚未用真实训练模型验证识别准确率，也未做FPGA器件映射/布局布线。
