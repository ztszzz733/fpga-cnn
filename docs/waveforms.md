# 波形查看指南

## GTKWave 窗口看不到时

直接运行：

```powershell
python scripts/view_wave.py --image
```

再双击以下图片即可查看，无需 GTKWave：

- [完整波形图](../build/wave_overview.png)：启动、忙、读写 RAM、完成和输出。
- [MAC 放大图](../build/wave_mac_detail.png)：逐周期累加到 45。

图片由 `scripts/render_wave.py` 从真实 `top_smoke.vcd` 逐次信号变化绘制，数字总线以十进制标注。此功能需要 Pillow，本机已有。只有图像导出步骤使用 Pillow，RTL 仿真本身不依赖它。

此前只检测进程仍在运行就打印“GTKWave opened”，不能据此确认窗口已经显示。启动脚本现已改为准确报告“process started”，并给出图片查看方式。当前电脑操作工具连续超时，尚未确认 GTKWave 窗口不可见的具体原因。

## 一条命令打开

在 `D:\code\FPGA1` 打开终端：

```powershell
python scripts/view_wave.py
```

该命令重新运行小规模卷积测试，确认 PASS 后启动本机 GTKWave，并加载预选信号。其他电脑需要将 GTKWave 加入 PATH，或设置 `GTKWAVE` 环境变量为可执行文件路径；Icarus 的工具位置仍由原有仿真脚本处理。

- [top_smoke.vcd](../build/top_smoke.vcd)：真实 RTL 仿真的波形数据。
- [top_smoke.gtkw](../build/top_smoke.gtkw)：19 个关键信号的布局。
- [tb_top_smoke.log](../build/tb_top_smoke.log)：对应测试日志。

GTKWave 初始视图会缩放到完整时间范围。横轴为时间，每一行是一条信号。点击波形可以定位某个时间，使用工具栏放大 / 缩小按钮查看细节。预选的多位总线按十六进制显示，例如 `2D` 就是十进制 45。

## 建议从这些信号看起

| 信号 | 观察内容 |
|---|---|
| `clk` / `rst_n` | 10 ns 时钟周期；低有效复位 |
| `start` | CONTROL.START 产生的一周期脉冲 |
| `core_busy` | Controller 正在运行 |
| `done` | 内核计算结束脉冲 |
| `error` | 本例无错误，复位后保持 0 |
| `mmio_rdata` | CPU 模拟读 STATUS：运行中 1，完成后 2 |
| `controller_state` | FSM 状态编码；例如 9=CONV、A=RELU、F=DONE |
| `mem_read` / `mem_write` / `mem_ready` | RAM 请求 / 应答；在上升沿完成握手 |
| `mem_addr` / `mem_wdata` | 物理 RAM 字地址、完整字写数据 |
| `mac_enable` / `tap` | 连续九次 MAC、窗口索引 0…8 |
| `input_value` / `weight_value` | 当前 MAC 输入值和权重 |
| `acc_value` | INT32 累加结果 |
| `output_value` | 写回前的 INT8 结果 |

`done` 是单周期内部事件，而 STATUS.DONE 是保持位。`core_busy` 不含 MMIO START 等待接收的那一个周期；软件看到的 STATUS.BUSY 已包含 START 等待阶段。

## 本例已核对的时间点

输入 3×3，值为 1…9；权重九个 1；Bias=0；无 padding、ReLU、池化和量化右移，结果为 45。

| 时间 | 波形变化 |
|---|---|
| 175 ns | `start` 上升 |
| 185 ns | `start` 下降，`core_busy` 上升 |
| 190 ns | Testbench 读取 STATUS，`mmio_rdata=1` |
| 785–865 ns | 每周期累加，十进制依次为 1、3、6、10、15、21、28、36、45 |
| 895 ns | `output_value=0x2D`，即 45 |
| 935 ns | `done` 上升 |
| 945 ns | `done` / `core_busy` 下降，STATUS 读值变为 2 |
| 951 ns | 所有结果检查通过，仿真结束 |

RAM 输出字节地址为 `0x401`，因此外部写地址为对齐后的 `0x400`，完整写数据为 `0xA5A52DA5`。目标 lane 写成 2D，其余三字节仍为 A5。

波形开头 0–5 ns 可能显示 X，这是仿真初始寄存器尚未经过首个有效复位时钟沿的状态；后续复位和正常计算都有明确值。

## 只生成文件 / 查看完整用例

```powershell
# 小例子，约 951 ns 的仿真时间
python scripts/run_tests.py top_smoke --waves

# 完整 Golden 回归，包含 224×224 图像
python scripts/run_tests.py cnn_accelerator --waves
```

后者生成 `build/cnn.vcd`，运行和打开所需时间明显更长。可以在 GTKWave 中打开对应 VCD，再从信号树选择 `tb_cnn_accelerator.dut` 下的信号。仿真时间与电脑执行耗时是不同概念。
