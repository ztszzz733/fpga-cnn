# 从接收任务到配置阵列的完整波形

本例通过真实 MMIO、任务读取器、任务等待窗口、卷积控制器、读取缓存、Memory IF、Data RAM 模型和 8×8 阵列执行。
任务为普通 1×1 卷积：输入 3×1×2，输出 2×1×2；stride=1，padding=0，quant_shift=0，无激活。
外部 Testbench 预置 RAM，写三次 MMIO，之后硬件自主读取任务和所有操作数。
没有实现 CPU，也没有修改生产 RTL。队列只有一条任务，等待窗口仍保持默认深度 4。

## 运行与打开

在项目根目录执行：

```powershell
python scripts/task_setup_wave.py --open
python scripts/task_setup_wave.py --open --view buffers
python scripts/task_setup_wave.py --open --view array
```

不加 `--open` 时只生成结果。三个视图来自同一份 VCD，不是三次不同内容的波形。
每条命令会重跑这个很小的仿真，然后打开指定视图；不生成图片。

- `build/task_setup_wave/queue.gtkw`：MMIO → 读描述符 → FIFO → 配置锁存。
- `build/task_setup_wave/buffers.gtkw`：读数据 → 拆包 → 装 bias/A/B 缓冲 → 启动阵列。
- `build/task_setup_wave/array.gtkw`：与上一份独立阵列例子相同的 PE 信号，但时间由完整流程决定。
- `build/task_setup_wave/guide.md`：自动生成的全部信号逐行解释、阶段时间、缓冲写入值、状态编号。
- `build/task_setup_wave/events.csv`：实际时钟沿采样的任务与内存事件。
- `build/task_setup_wave/comparison.csv`：68 项 PE 的 Python/RTL 整数对照。
- `build/task_setup_wave/output.csv`：最终 RAM 输出。

上面路径相对于 `mobilefacenet`。打开 `.gtkw` 可以恢复预选信号及有符号十进制格式；`.vcd` 是原始波形数据。

## 默认数据

沿用 `examples/systolic_wave.json`。可以修改后重新运行；维度固定，允许改变 INT8 输入/权重和 INT32 bias。
默认最终结果是 42、60、8、14，与独立阵列例子一致。

输入窗口为 `[4,5,6]`、`[7,8,9]`，按真实 CHW 内存格式存储为 `[4,7,5,8,6,9]`。
控制器从 RAM 读取后会重新排列成窗口顺序。可以观察 B 缓冲依次写入 4、5、6、7、8、9。

队列基址为 `0x1000`，任务数为 1，CONTROL 写 `0x3D`。
描述符的八个 32 bit 字为：

| 索引 | 值 | 作用 |
|---|---|---|
| 0 | 0x00000100 | version=1，OP=0 普通卷积 |
| 1 | 0x00000101 | 输入地址 |
| 2 | 0x00000401 | 输出地址 |
| 3 | 0x00000201 | 权重地址 |
| 4 | 0x00000300 | Bias 地址 |
| 5 | 0x00010002 | height=1，width=2 |
| 6 | 0x00020003 | OC=2，IC=3 |
| 7 | 0x00000011 | kernel=1，stride=1，其余关闭 |

## 关键时间（默认 RAM 等待配置）

所有时间指接受操作的上升沿，而非信号刚拉高的时刻。

| 时间 ns | 事件 |
|---|---|
| 35、55、75 | 三次 MMIO 写入队列基址、任务数、START |
| 85 | 队列接受启动脉冲 |
| 135～415 | 读取 8 个描述符字 |
| 435 | 描述符入 FIFO |
| 445 | 任务出队，卷积控制器锁存配置 |
| 515、595 | Bias 缓冲写入 10、-5 |
| 675～835 | A 缓冲写入 1、2、3、-1、1、2 |
| 915～1175 | B 缓冲写入 4、5、6、7、8、9 |
| 1185 | tile 接受 start，锁存 rows=2、cols=2、depth=3 |
| 1195 | 各 PE 装 bias |
| 1205 | PE00 第一次乘加 |
| 1225 | 四个有效 PE 同时乘加 |
| 1245 | 四个累加结果均计算完毕 |
| 1735 | 整条队列结束，STATUS 置 DONE |

查看控制和输入值时把光标放到上升沿之前，查看锁存/累加后的结果时放到上升沿之后。
例如 `tile_start` 在 1175 ns 更新后已为 1，但 tile 在 1185 ns 才接受启动。

脚本校验完整描述符、14 次缓冲写入及先后顺序、配置锁存、阵列有效范围、每拍 PE 对齐和累加、最终 INT8 输出。
RAM 模型还检查等待期间地址/控制保持稳定；Testbench 检查输出之外的同字节边界未被读改写破坏。
