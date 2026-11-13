# CNN 实际代码整合修改说明（小白版）

更新：2026-10-08。依据用户最新要求，改 SRAM 时序、把仲裁并入 datasram，同时实现 UART 图像桥和时钟复位模块。
输入仍是 `D:\QQ\FPGA1.zip` 和 `cpu_internal_ram_integration.md`，原始资料保留。

## 1. 一句话说明

**CPU 只保留执行功能；IEM 和 datasram 独立平级。CNN 直接连接 datasram 的原生完成接口，仲裁在 datasram 内，板级顶层实际只有六个大模块。**

这不是单纯把旧框改个名字。新 datasram 自己实现 RAM 数组、A/B 时序和内部仲裁；当前顶层不再实例化旧 CPU 存储子系统或独立 B 口仲裁器。

## 2. 哪些没动

原 CPU 的 Control C1、Datapath 十二个生产模块、ALU、流水线、寄存器堆、前递、分支逻辑都保持原有实现。因为 A 口固定一拍时序没有变化，它们不需要加等待信号。

CNN 的 `partners/cnn/FPGA1/rtl` 保留收到的原包内容，CPU MMIO 接它自带 accelerator_regs，存储口接它自带 accelerator_mem_if。没有用旧假 CNN 模块替换实际 CNN。

XSim 不接受原包 tensor_operator_engine 的一处声明写法，当前编译使用 `rtl/compat/tensor_operator_engine.sv` 的语法等价副本：把带初始化的 wire 声明拆为 wire 声明和 assign。只改此语法，不改计算逻辑；原包文件仍保留。

## 3. 具体改了哪些文件

| 文件 | 本次作用 |
|---|---|
| rtl/soc/cpu_core.sv | 新执行核边界，内部连接原 cpu_control 和 cpu_datapath，向外暴露 imem/dmem/mmio |
| rtl/soc/datasram.sv | 新共享 RAM 实现：CPU 固定一拍 A 口、CNN 原生 ready 完成时序、图像桥 req/gnt/rvalid/error；内部仲裁 |
| rtl/soc/image_bridge.sv | UART 8N1、CRC32、最多 256 字节分块传输、SRAM 读回、错误回复与超时恢复 |
| rtl/soc/clock_unit.sv | 时钟直通，低有效复位异步置位、三拍同步释放 |
| rtl/soc/face_soc_top.sv | 板级顶层，直接实例化六个大模块，7 根总体数字 I/O |
| rtl/soc/face_soc_cnn_top.sv | 更新为四个平级模块的 CPU/CNN 测试入口，不是板级顶层 |
| rtl/filelists/system_cnn.f | 当前完整系统编译清单；去掉旧存储子系统、独立 B 仲裁器和假 CNN 寄存器依赖 |
| tb/integration/tb_cnn_native_memory.sv | 原生 SRAM 时序、争用、故障和复位测试，直接测 datasram |
| tb/integration/tb_cpu_cnn_integration.sv | 真实 CPU 程序 + 原 CNN + 新 SRAM，结果和事务计数检查 |
| tb/integration/tb_soc_uart.sv | 六模块板级实例、真实串口波形、CRC、读写、争用、错误、超时、复位验证 |
| scripts/run_cnn_integration.py | 统一运行上述三套 XSim 测试并记录每次源码哈希和独立结果 |
| scripts/uart_image_transfer.py | 电脑分块写入、读回及可选读回校验工具 |
| tb/test_uart_image_transfer.py | 不用板卡的主机协议单元测试 |
| scripts/draw_soc_cpu_mem_io.py | 重画六模块横向 PNG/SVG，并同步顶层接线说明 |

旧 `partners/datapath/delivery/rtl/soc_memory/` 里的 wrapper、data_sram_tdp、sram_b_arbiter 没有删除，以免破坏历史 B1 回归；当前板级编译不用它们。IEM 继续复用其中 imem_rom。早前放进旧 wrapper 的兼容措施只属于历史路径，不能拿它解释现在六模块顶层。

## 4. SRAM 时序到底怎么改

CPU A 口照旧：上升沿采样读地址，沿后返回数据；写数据和字节使能在上升沿提交。没有增加可变等待，所以原 CPU 不用改流水线。

CNN B 口直接支持“请求保持到 mem_ready”。读请求接收后先取得正确 SRAM 数据，再用一个完整周期给 ready；这期间记住本次属于谁，不重复接单。写请求则在确认成功的上升沿写入并完成。CNN 不再先转换成一套外部 70/35 位接口再找仲裁器。

图像桥仍用 70/35 位接口：写随 gnt 完成，读先 gnt 后 rvalid，error 保留。桥不能把 gnt 当成读数据已经到达。

内部 B 口 CNN 优先；在途读完成前不能被另一主设备抢走。CPU A 与 B 同字且至少一边写，A 优先、B 报错；不同字可并行。软件仍须管理图像/权重/结果的所有权，硬件仲裁不是整帧锁。

CNN 原接口没有 error。错误时 datasram 锁存 cnn_mem_fault，不假成功；CNN 可能停止等待，需系统复位。UART 内存超时也回错误包并停机到复位；普通 CRC 错误只亮锁存错误灯，回包后可以重传。

## 5. 新手从哪里看

1. 先看顶层 [六模块连线与总体 I/O](../SoC顶层连线与总体IO说明_小白版.md)：全部连线分地址、数据、信号三组，逐根写方向和位宽。
2. 再看 [横向芯片连接图](SoC芯片封装与内部IO层级连接图.md)：左 CPU + 存储器，右 CNN + I/O，仲裁不单独画框。
3. 要串口传图，看 [UART 协议与命令](uart_image_bridge_protocol.md)：传的是 raw 字节，不能直接让硬件解码 JPEG。
4. 看 [本次验证记录](soc_six_module_verification_20261008.md)：区分 RTL 测试通过与真正上板通过。

## 6. 还不能误认为已经完成的事情

UART 和 clock_unit 已有可仿真的实际 RTL，不再是空壳；但当前没有指定 FPGA 型号/引脚，没有 PLL 和按键去抖，没有自动生成完整人脸识别固件，也没有承诺完整 CNN 模型识别精度。
上板前需准备 IMEM_INIT_FILE 固件、地址所有权协议、实际 CLOCK_HZ、引脚电压/时钟约束，以及 BRAM 推断与布局布线时序验收。复位不清空 SRAM，固件必须初始化数据。
