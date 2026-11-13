# CPU 侧对 CNN 的接口与代码交付说明

日期：2026-10-08。接收方：FPGA1 / CNN 开发者。

本说明对应当前 CPU_CONTROL 工程的实际 RTL。CPU 使用 Control C1 与生产 Datapath；CNN 对接版本是 `FPGA1.zip` 内的任务队列版 `mobilefacenet_accelerator_top`。本次交付复制现有代码，不修改双方计算逻辑。

## 1. 连接结构与分工

当前板级顶层为 `rtl/soc/face_soc_top.sv`，直接实例化六个平级模块：

```text
clock_unit ── clk/rst_n ── 各模块
imem_rom ── 指令 ── cpu_core（Control + Datapath）
cpu_core ── MMIO 配置/状态 ── mobilefacenet_accelerator_top
cpu_core ── dmem_* A口 ── datasram
CNN      ── mem_* B侧 ── datasram
image_bridge ── io_mem_* B侧 ── datasram
```

CPU 通过普通 LW/SW 配置 CNN 并查询状态；CNN 自主从共享 SRAM 读取任务、图像、权重并写回结果。CNN 访存直接到 `datasram`，不经过 CPU 执行核心。SRAM B 侧仲裁及完成时序已经集成在 `datasram` 内。

CPU 方交付：CPU 核心、共享定义、SRAM、指令 ROM、时钟复位、UART 图像桥、系统接线和联调测试。CNN 方保留自己的任务调度、算子和内部访存逻辑。CNN 不需要接入 CPU 内部流水线控制信号，也不需要 CPU 新增专用 CNN 指令。

## 2. CPU 与 CNN 的 MMIO 端口

下表方向以 CNN 模块为参照；所有地址均为字节地址。

| CNN 端口 | 方向 | 位宽 | CPU 对端 / 含义 |
|---|---|---|---|
| `clk` | 输入 | 1 | 系统公共时钟 |
| `rst_n` | 输入 | 1 | 系统公共低有效复位 |
| `mmio_addr` | 输入 | 32 | `cpu_core.mmio_addr`，完整地址，含基址 |
| `mmio_wdata` | 输入 | 32 | `cpu_core.mmio_wdata`，寄存器写数据 |
| `mmio_we` | 输入 | 1 | `cpu_core.mmio_we`，写请求 |
| `mmio_re` | 输入 | 1 | `cpu_core.mmio_re`，读请求 |
| `mmio_rdata` | 输出 | 32 | 返回 `cpu_core.mmio_rdata` |
| `mmio_ready` | 输出 | 1 | 返回 `cpu_core.mmio_ready` |

顶层以 `cnn_mmio_*` 连线连接双方同名端口。CPU 和 CNN 的基址由同一个顶层参数 `CNN_MMIO_BASE` 设置，默认 `0x4000_0000`。

**CPU MMIO 是零等待接口。** 合法请求所在周期必须组合给出 `mmio_ready=1`，读操作同周期给出有效 `mmio_rdata`，写操作在请求有效的上升沿接收。当前 Datapath 不会因 `mmio_ready=0` 停住流水线或重试。因此不能把 CNN 寄存器读响应改成下一拍，也不能用 `ready=0` 表示 CNN 正在计算。计算忙应通过 STATUS 返回；现有 CNN RTL 符合此约定。

CPU 只对 4 字节对齐的 LW/SW 发出 CNN MMIO 请求，没有字节使能。CPU 不会把 SB/SH、非对齐字访问或窗口内未列出的地址转发为合法 CNN 请求。不要依赖这些非法访问触发异常或重试。

## 3. 当前寄存器和软件调用顺序

CPU 的 MMIO 译码窗口默认 4 KiB，合法寄存器槽位为基址加 `0x00, 0x04, …, 0x20`。CNN 当前只使用以下四项；其余五个槽位读零、写忽略。

| 地址 | 名称 | 用途 |
|---|---|---|
| `0x4000_0000` | CONTROL | bit0 START，bit1 软件 RESET，bits5:2 模式；队列启动写 `0x3D` |
| `0x4000_0004` | STATUS | bit0 BUSY，bit1 DONE，bit2 ERROR；只读 |
| `0x4000_0008` | QUEUE_BASE | SRAM 中任务描述符队列的字节地址 |
| `0x4000_0018` | TASK_COUNT | 任务数量 |

建议按以下顺序调用：

1. 确认 CNN 空闲；在 SRAM 中准备描述符、输入、权重、参数和输出空间，避免与 CPU/图像桥正在写入的区域重叠。
2. 用 SW 写 QUEUE_BASE 和 TASK_COUNT。描述符字段、算子参数及张量布局沿用 FPGA1 的定义。
3. 用 SW 向 CONTROL 写 `0x3D`，进入模式 15 并触发 START。
4. 用 LW 轮询 STATUS，同时检查 ERROR，并设置软件超时。DONE 后从共享 SRAM 读取结果，不能从 `mmio_rdata` 读取特征向量。
5. 必要时写 CONTROL=`0x02` 请求 CNN 软件复位，再确认状态。软件复位不会清除系统 `cnn_mem_fault`。

START/RESET 位读回为零；DONE/ERROR 是锁存状态，接受新启动或软件复位时清除。CNN 忙或正在处理启动/复位时，队列配置不能更新；忙时重复启动会置 ERROR。不要把 MMIO 握手成功理解成任务执行成功。

这只是驱动顺序，交付包未提供完整人脸识别固件、链接脚本或模型数据。可执行的最小 CPU 机器码联调样例见 `tb/integration/tb_cpu_cnn_integration.sv`，测试在仿真内装载程序和数据。

## 4. CNN 与共享 SRAM 的端口及握手

| CNN 端口 | CNN 方向 | 位宽 | 对端 |
|---|---|---|---|
| `mem_addr` | 输出 | 32 | `datasram.mem_addr`，字节地址 |
| `mem_wdata` | 输出 | 32 | `datasram.mem_wdata` |
| `mem_read` | 输出 | 1 | `datasram.mem_read` |
| `mem_write` | 输出 | 1 | `datasram.mem_write` |
| `mem_rdata` | 输入 | 32 | `datasram.mem_rdata` |
| `mem_ready` | 输入 | 1 | `datasram.mem_ready`，本次访问完成 |

请求共 66 位、返回共 33 位，不含公共时钟复位。采用现有 CNN 原生协议，无 `gnt/rvalid/error/be` 端口。

- 同时最多一笔在途；`mem_read` 和 `mem_write` 不能同时为 1。请求方保持请求、地址和写数据，直到在上升沿采到 `mem_ready=1`，然后结束或切换下一笔。
- 写：无竞争、合法时，SRAM 可以在本周期给出 ready，并在该上升沿写入；不能假定所有访问都必须先等待一拍。
- 读：在 SRAM 接收读请求的上升沿锁存数据，随后响应周期同时给出有效 `mem_rdata` 与 ready，CNN 在下一个上升沿接收。不能在数据尚未有效时提前给读 ready。
- 地址须在 SRAM 范围内且 4 字节对齐。CNN 外部写入是整字写；INT8 字节写由 CNN 自己的 `accelerator_mem_if` 做读改写。
- SRAM 默认范围 `0x0000_0000`～`0x0003_FFFF`，256 KiB。CPU、CNN、图像桥都使用同一字节地址空间；容量须与模型内存规划核对。

CPU A 口固定一拍同步读、按字节使能写，不能增加等待。CNN 与图像桥共享 B 侧，CNN 优先；在途读保留返回归属。长时间 CNN 流量可能延迟图像桥，软件应分配上传与计算时段。

CPU A 与 B 同周期访问同一字且任一方写入时，B 侧报故障；双方只读允许。CNN 读改写的两个阶段也不是跨主设备原子操作，因此其他主设备不能同时改同一输出字。软件应划分互不冲突的缓冲区及所有权。

CNN 原生没有错误返回口，非法地址、非对齐访问、同时读写或冲突会锁存系统侧 `cnn_mem_fault`，失败事务不给 CNN 成功 ready；恢复需要系统复位。图像桥使用另一套 `io_mem_*` 70/35 位接口并保留 `error`，不能把它当作 CNN 原生接口接线。

## 5. 时钟、复位和程序入口

所有模块当前处于同一时钟域。`clock_unit` 时钟直通、不带 PLL；外部复位异步拉低，三拍同步释放。系统复位清除控制状态，不清空 SRAM 内容，软件必须先初始化有效数据。

指令 ROM 与数据 SRAM 分离，虽默认都从地址 0 开始，属于不同访问路径。指令 ROM 默认 64 KiB，复位 PC 为 0；实际程序需通过 `IMEM_INIT_FILE` 提供 `$readmemh` 格式内容。空文件参数不代表已有可运行应用。

CPU 实现当前约定的 37 条 RV32I 指令，不含乘除法、CSR、特权、压缩、原子扩展或异常处理；Control 保持组合逻辑，流水线状态由 Datapath 持有。

## 6. 代码包目录和接入方法

压缩包根目录 README 提供本说明入口，目录保留工程中的相对路径：

| 目录/文件 | 内容 |
|---|---|
| `rtl/cpu_control/` | 用户 Control C1 六个模块 |
| `partners/datapath/delivery/rtl/common/` | 生产系统使用的唯一 `cpu_control_pkg.sv` |
| `partners/datapath/delivery/rtl/cpu_datapath/` | 12 个生产 Datapath 模块 |
| `partners/datapath/delivery/rtl/soc_memory/imem_rom.sv` | 当前指令 ROM |
| `rtl/soc/` | CPU 封装、SRAM、两个顶层、时钟复位与图像桥 |
| `rtl/compat/tensor_operator_engine.sv` | XSim 所需的 CNN 语法等价副本，单独隔离 |
| `rtl/filelists/cpu_side.f` | 包内 CPU/系统支持源码清单，不含依赖 CNN 的系统顶层和 CNN 兼容模块 |
| `rtl/filelists/system_cnn.f` | 完整联调清单，需补入 CNN 原始目录 |
| `tb/integration/` | 三个系统联调测试 |
| `scripts/run_cnn_integration.py` | XSim 联调入口 |
| `scripts/run_tests.py` | 原工程脚本，供联调入口导入工具定位/执行函数；本精简包不附其完整 Control/stub 测试资源，不单独运行它 |
| `scripts/uart_image_transfer.py`、`tb/test_uart_image_transfer.py` | UART 主机工具及协议单元测试 |
| `SHA256SUMS.json` | 除清单自身外所有交付文件的 SHA256 |

完整 CNN 原始源码不重复放进 CPU 包。请将自己的 `FPGA1/rtl/` 放到解压根目录 `partners/cnn/FPGA1/rtl/`，使用以下版本：

`FPGA1.zip SHA256 = 3c3e6b390c8ade24e65a8864db3dc962c92b2411f8391b8cc9ceceaf3b6b016c`

在解压根目录执行：

```powershell
python scripts/run_cnn_integration.py
python -m unittest discover -s tb -p test_uart_image_transfer.py
```

需要 Python 3 和 Vivado XSim；本机验证版本为 Vivado 2026.1。其他机器应先设置 Vivado 工具环境，必要时设置 `XILINX_VIVADO` 指向 Vivado 安装根目录。运行会在包内 `build/runs/` 创建独立结果目录。

手动建 Vivado 工程时按 `system_cnn.f` 以 SystemVerilog 模式加入源文件，路径相对于解压根目录；板级顶层选 `face_soc_top`，计算侧仿真使用 `face_soc_cnn_top`。禁止同时加入兼容版和原版 `tensor_operator_engine`；不递归加入旧同名模块、旧 `cnn_mmio_regs`、旧外置 SRAM 仲裁器或历史存储子系统。

`cpu_side.f` 用于只查看/编译 CPU 与系统支持模块，不代表完整 CNN SoC。它也不另行加入根目录历史 `rtl/common/cpu_control_pkg.sv`，避免重复定义。

## 7. 验证范围与后续配合

当前工程已通过三项 XSim 测试：CNN 原生存储握手；真实 CPU 下发 CNN 小任务并读回 17、19；六模块顶层 UART 位级传输。另有 7 项 UART 主机协议单元测试通过。代码包还会在独立解压目录补入指定 CNN 源码后重新跑这三项测试，具体交付复核结果随包外同名核验文件提供。

本结果不代表 FPGA 上板、综合资源足够、布局布线时序通过或完整 MobileFaceNet 精度验收。下一阶段需双方核对实际模型容量、描述符/缓冲区布局、应用固件以及板卡时钟和引脚约束。改变 CNN 外部端口、MMIO 零等待要求或访存完成语义之前，需要同步调整并重新验证系统接口。
