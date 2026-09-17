# 自己修改任务队列的输入并看输出

这是便于手算的教学实验：一次START，从RAM取出并执行3条任务：

```text
输入3×3单通道 → 3×3卷积得到1个值 → 1×1卷积得到128个值 → FINAL写回RAM
```

## 改哪里

打开 `mobilefacenet/examples/custom_queue_input.json`，修改 `input` 中的数字并保存。保留3行3列，每个数字是-128～127的整数。

```json
"input": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
```

默认第一层权重全为1、Bias=0，不右移、不激活。因此第一层输出是 `1+2+…+9=45`。第二层的128个输出通道都使用权重1、Bias=0，所以最终128个值全部为45。这是手算实验，不是训练好的人脸特征。

**只把最后的9改成10，其他保持默认，输出就应从45变成46。**

## 每次修改后运行

在工程根目录运行：

```powershell
python mobilefacenet/scripts/custom_queue.py
```

程序重新计算Python预期结果，生成RAM与任务表，在真实RTL中运行队列，比较9次乘加、每层RAM结果和最终128字节。终端打印 EXPECTED、ACTUAL 和 PASS；同一输出目录再次运行，还会打印与上次相比改变了几个最终字节。失败会非零退出。

## 先看图片，再看交互波形

运行后打开 `mobilefacenet/build/custom_queue/` 中：

| 文件 | 用途 |
|---|---|
| wave_mac_detail.png | 放大的第一层乘加与输出波形，直接双击图片即可看 |
| wave_overview.png | 完整队列：一次START、依次执行3条任务、最后DONE |
| comparison.md | 每一步正确结果、RTL实际结果及对应时间，按表找波形 |
| actual_mac.csv | 第一层9次实际乘加采样 |
| actual_outputs.csv | 各任务输出锁存值、地址和时间 |
| ram_comparison.csv | 257个层输出字节的预期值和RAM实际值 |
| features.actual.bin | 最终128字节，signed INT8 |
| custom_queue.vcd | GTKWave可打开的交互波形；VVP不是波形 |
| case_used.json | 本次实际使用的输入快照 |
| result.json | 本次是否通过，以及完整128维期望结果 |

波形中 `av` 是本次乘加的输入，`wv` 是权重，`normal_result` 是累加结果，`out_value` 是量化后的输出。默认最终第一层 `normal_result=45`、`out_value=45`。

表格中的时间是对应上升沿后1ns，便于看到已经更新的结果；输入则在该沿之前采样。默认参数下第一层最后累加采样为2036ns、输出采样为2056ns，实际以每次生成的表格为准。

需要交互缩放时运行：

```powershell
python mobilefacenet/scripts/custom_queue.py --open
```

也可以直接打开现有波形，不重新仿真：

```powershell
python mobilefacenet/scripts/view_wave.py --vcd mobilefacenet/build/custom_queue/custom_queue.vcd --scope tb_task_queue.dut
```

## 其他可修改项

| JSON字段 | 含义 |
|---|---|
| weight | 第一层3×3权重，-128～127 |
| bias | 第一层INT32 Bias |
| quant_shift | 第一层算术右移位数，0～255 |
| relu_enable | 第一层负数是否截为0 |
| relu6_enable | 第一层是否限制在整数域0～96 |
| projection_weight | 第二层128个通道共用的INT8权重 |
| projection_bias | 第二层128个通道共用的INT32 Bias |
| projection_quant_shift | 第二层右移位数 |

第二层每个输出为 `sat_int8(wrap_int32(第一层INT8输出 × projection_weight + projection_bias) >>> projection_quant_shift)`。两层之间存的是INT8；第一层已经量化与饱和。

修改输入后输出可能不变：右移丢掉低位、ReLU清零负数、或饱和截到-128/127。先看comparison.md中的累加、右移和激活结果，再判断原因。

实验运行只生成build目录中的产物，不修改输入文件。之前单算子的 `custom_input.json` 和 `custom_wave.py` 仍单独保留。此实验不注入故意的非法任务，正常结束STATUS=2；原完整异常回归继续使用 `run_tests.py task_queue`。

工具自身的四组回归可用 `python mobilefacenet/scripts/test_custom_queue.py` 复现：默认45、改输入46、负数右移-23、ReLU6加第二层饱和127。测试使用独立输入文件，不改动你的JSON。
