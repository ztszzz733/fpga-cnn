# 纯脉动阵列加速器

当前版本只执行普通 Conv 和 Depthwise，两者共用一套 8×8 脉动阵列。
不包含 CPU、SoC、独立标量卷积引擎、ReLU/ReLU6、ADD、COPY、FINAL_OUTPUT 通路。
保留任务队列、9 个 MMIO 寄存器和原来的 32 bit RAM master 接口。

**所有算子必须通过RAM任务队列提交，已取消CPU直接配置单算子的方式。**
CPU只写任务表地址（0x40000008）、任务条数（0x40000018）和CONTROL=0x3D。
原OUTPUT_ADDR、WEIGHT_ADDR、BIAS_ADDR、CHANNELS、LAYER_PARAM的MMIO位置保留，读0、写无效。
这些参数都从每条32字节任务描述符取出；只执行一层时，提交一条任务的队列即可。

支持普通1×1/3×3 Conv、3×3/7×7 Depthwise、stride、padding和分块尾部处理。
输入/权重是 signed INT8，Bias/累加是 signed INT32；结果算术右移并饱和到 signed INT8 后写回 RAM。
最后一层卷积直接输出128个特征，无需 FINAL_OUTPUT 任务。

**本版本不支持完整 MobileFaceNet 的激活与残差。旧模型任务表不能直接用于当前硬件。**

## 仿真与波形

在项目根目录运行：

```powershell
python mobilefacenet/scripts/verify_all.py
python mobilefacenet/scripts/accelerator_wave.py --open --view timing
```

第二条运行9条纯卷积/Depthwise任务，打开任务切换、供数、阵列计算、写回的波形。
每行含义和实际时间点见 build/accelerator_wave/timing_guide.md。
示例逐层比较980个INT8结果，最后一层直接写出128个特征。

```powershell
python mobilefacenet/scripts/systolic_wave.py --open
python mobilefacenet/scripts/task_setup_wave.py --open
python mobilefacenet/scripts/check_structure.py
python mobilefacenet/scripts/synthesize_systolic.py
```

前两条查看阵列内部和任务配置。结构检查确认64个PE及被移除的模块不在顶层中。
综合输出 build/array_only_synthesis/synthesis_summary.json，仅为通用逻辑统计，非 FPGA LUT/DSP/BRAM 或最高频率。

## 文件入口

- [结构和兼容性](docs/array_only.md)
- [唯一提交入口：任务队列](docs/task_queue.md)
- [时序波形说明](docs/accelerator_wave.md)
- 当前RTL：rtl/*.sv；测试：tb/；入口：scripts/run_tests.py。
- 旧版模块、测试和脚本已移到 legacy/，不参与默认编译。

旧文档和旧性能报告仅记录历史版本。ONNX导出器仍支持离线BatchNorm融合，但会拒绝需要激活/残差/复制的模型，不会悄悄删除运算。
