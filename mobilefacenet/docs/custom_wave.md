# 自己修改输入、对照每一次乘加

这是一个专门用于手算核对的小实验：单输入通道、单输出通道，输入3×3、卷积核3×3、stride=1、padding=0，只产生一个输出。调用的是工程中的真实加速器顶层，经过MMIO配置、RAM读取、缓冲、MAC、量化和RAM写回。没有故意插入重复START或非法配置。

## 修改与运行

修改 [examples/custom_input.json](../examples/custom_input.json)，保存后在工程根目录运行：

```powershell
python mobilefacenet/scripts/custom_wave.py
```

不需要手动编译VVP。程序会先计算正确答案，再运行RTL，检查9次乘加与最终RAM结果，最后生成真实VCD波形图片。默认输入文件不会被脚本改写。

可编辑字段：

| 字段 | 可填内容 |
|---|---|
| input | 3行×3列，每个数为-128～127的整数 |
| weight | 3行×3列，每个数为-128～127的整数 |
| bias | -2147483648～2147483647的整数 |
| quant_shift | 0～255的整数 |
| relu_enable | true或false |
| relu6_enable | true或false，上限为整数96 |

JSON中不要添加注释或多余的逗号。先保持矩阵大小不变，只修改里面的数字。输入数值无需随机生成，设置正数、负数、零或不同权重都可以。需要另存多个案例时：

```powershell
python mobilefacenet/scripts/custom_wave.py --input D:/my_cases/negative.json
```

## 默认案例的正确答案

```text
输入              权重
1  2  3           1  1  1
4  5  6           1  1  1
7  8  9           1  1  1

bias=0，quant_shift=0，ReLU/ReLU6关闭
```

从左到右、从上到下做9次乘加：

| 次数 | tap | av | wv | normal_result（该上升沿更新之后） |
|---|---|---|---|---|
| 1 | 0 | 1 | 1 | 1 |
| 2 | 1 | 2 | 1 | 3 |
| 3 | 2 | 3 | 1 | 6 |
| 4 | 3 | 4 | 1 | 10 |
| 5 | 4 | 5 | 1 | 15 |
| 6 | 5 | 6 | 1 | 21 |
| 7 | 6 | 7 | 1 | 28 |
| 8 | 7 | 8 | 1 | 36 |
| 9 | 8 | 9 | 1 | 45 |

最终 out_value=45；RAM地址0x401的字节为0x2d；STATUS=2。实测默认时序的9个采样沿为955、965、975、985、995、1005、1015、1025、1035ns；具体运行应以自动生成的对照表为准。

## 查看结果

输出集中在 `mobilefacenet/build/custom_wave/`：

- `comparison.md`：最适合手工核对，列出每次采样的时间、输入、权重、预期累加和RTL累加。
- `wave_mac_detail.png`：放大后的真实累加波形，包含clk、sv、tap、av、wv、normal_result、out_we和out_value。
- `wave_overview.png`：从启动到写回完成的真实波形。
- `custom.vcd`：完整DUT信号，供GTKWave缩放与查看。
- `expected_steps.csv` / `actual_steps.csv`：Python计算数据与RTL实测数据。
- `case_used.json`：本次运行使用的输入快照。
- `result.json`：本次验证状态和最终预期值，全部检查成功才是passed。

想同时启动GTKWave：

```powershell
python mobilefacenet/scripts/custom_wave.py --open
```

GTKWave预设的多位数据使用十六进制；手工核对负数时可选有符号十进制，或直接看PNG，它已按有符号十进制绘制。此实验输出为单独的custom.vcd，不覆盖原来mobilefacenet.vcd。

## 如何按时间对照

在sv与engine_ready都为1的上升沿接收一对输入/权重。tap、av、wv应看该沿更新之前的值；normal_result应看该沿更新之后的值。控制器也会在同一个沿切换tap，所以不要把更新后的tap和上一项累加直接当成一对。

out_we有效的上升沿保存量化结果，之后out_value才改变。sv为0时，Buffer装载导致的av/wv变化不算乘加；未使用的位置出现X不能直接判断为计算失败。testbench只在有效采样时检查运算数，并在每次累加后比较预期结果。

例如955ns之前av=1、wv=1，955ns更新后的累加值=1；965ns之前av=2，965ns更新后的累加值=3。9次结束后，再等待out_we把45保存到输出缓冲。

## 可以自己尝试的修改

下表均以默认输入1～9为基础；“全1/全-1/全10”指9个权重都设置为该值。每行未启用的激活开关均设为false。

| 权重 | bias | shift | 激活 | 预期最终累加 | 预期INT8输出 |
|---|---|---|---|---|---|
| 全1 | 10 | 0 | 无 | 55 | 55 |
| 全1 | 0 | 1 | 无 | 45 | 22 |
| 全-1 | 28 | 2 | 无 | -17 | -5 |
| 全-1 | 28 | 2 | ReLU | -17 | 0 |
| 全10 | 0 | 0 | 无 | 450 | 127 |
| 全10 | 0 | 0 | ReLU6 | 450 | 96 |

注意负数算术右移：-17>>>2=-5。ReLU/ReLU6和饱和发生在累加结束之后，所以normal_result仍然可以是负数或超过127，out_value才是最终INT8。

源码：[custom_wave.py](../scripts/custom_wave.py)负责读取输入和独立手算；[tb_custom_wave.sv](../tb/tb_custom_wave.sv)负责驱动真实硬件、记录和检查。图片只读取VCD中的实际信号，没有用Golden数据伪造曲线。
