# 六模块 SoC 实现与验证记录

日期：2026-10-08。当前顶层 `rtl/soc/face_soc_top.sv`，清单 `rtl/filelists/system_cnn.f` 共 51 个源文件。
本报告替代 2026-10-07 的 CPU 存储子系统方案作为当前结构说明；早期结果保留作历史记录。

## 1. 本次结构核对

板级顶层直接实例化且只实例化六个大模块：

| 实例 | 类型 |
|---|---|
| u_cpu_core | cpu_core |
| u_cnn | mobilefacenet_accelerator_top |
| u_datasram | datasram |
| u_imem | imem_rom |
| u_image_bridge | image_bridge |
| u_clock_unit | clock_unit |

datasram 直接实现存储数组、A/B 访问、内部 B 仲裁、读返回归属、CNN ready 和错误锁存。当前清单不包含独立 sram_b_arbiter、cnn_memory_adapter、datapath_memory_subsystem、face_soc_cpu_memory_top、data_sram_tdp、cnn_mmio_regs。
`face_soc_cnn_top` 是四模块计算测试入口，保留用于定向 CPU/CNN 测试，不是板级顶层。

## 2. 实际 XSim 结果

执行：`python scripts/run_cnn_integration.py`。

本次最终目录：
`build/runs/20261008_010101_787590_cnn_integration/`。

[结果 JSON](../build/runs/20261008_010101_787590_cnn_integration/result.json) 包含当前 RTL 和 TB 的 SHA256；该目录还包含 compile.log、三个独立仿真日志和三个 VCD，不借用旧波形。

| 测试 | 结果 | 覆盖 |
|---|---|---|
| tb_cnn_native_memory | PASS | CNN 连续读写、读不提前 ready、不重复接单、图像桥在途读归属、范围/对齐/非法同时读写、A/B 冲突、复位清在途状态、CPU 字节使能和同步读、同字双读、IO 读错误和零字节写拒绝 |
| tb_cpu_cnn_integration | PASS | 实际 Control + Datapath 执行程序，经真实 MMIO 配队列；原 CNN 执行小任务结果 17 再 19，保护字节不变；非法 MMIO 宽度/对齐、不支持描述符、STATUS/软复位、CPU A 与 CNN/图像模拟主机 B 并发 |
| tb_soc_uart | PASS | 六模块实际板级实例；CPU 跑空闲循环；真实 UART 位级 256 字节非对齐写入和读回、请求/回复 CRC、边界保护、错误命令、断包超时、错误停止位、B 等待、A 冲突 error、读响应超时停机及复位恢复、三拍复位释放、复位保留 RAM 内容 |

注意：UART 测试中的短时 CNN 占用、CPU A 口冲突、丢失读返回用 TB force/release 注入，用于检查异常路径，不称为软件自然触发。真实 CNN 算法与真实 CPU 程序并发由另一条 tb_cpu_cnn_integration 覆盖。
未宣称在一条完整固件流程中完成“电脑上传整张脸 → 全模型 CNN 推理 → 身份识别输出”；该应用固件与模型验收仍待集成。

## 3. 主机协议与 Control 回归

执行：`python -m unittest discover -s tb -p test_uart_image_transfer.py`。
结果：7 项 PASS，覆盖请求格式/CRC、分段接收、读返回、写确认、坏 CRC、桥错误、超时和无效参数。测试用模拟串口对象，不需要 pyserial，不是物理串口测试。

执行：`python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot`。
结果目录：`build/runs/20261008_005522_079180_17092_all_seed1/`。
[结果 JSON](../build/runs/20261008_005522_079180_17092_all_seed1/result.json)：1,244 场景、30,463 检查、0 失败、1,000 随机译码，波形与图在此独立目录。该入口是 Control/stub 回归，其 real_datapath 字段不是本次真实 CPU/CNN 集成测试的结论；真实对接看上一节。

## 4. 原始代码核对

执行：`python scripts/audit_soc_sources.py`。
目录：`build/runs/20261008_010523_028747_soc_source_audit/`。
[核对 JSON](../build/runs/20261008_010523_028747_soc_source_audit/result.json)：

- CNN 的 25 个 `.sv` 与 `D:/QQ/FPGA1.zip` 内对应原文件逐字节相同。
- Datapath 的 12 个 `.sv` 与 `D:/QQ/face_recognition_soc_datapath_complete.zip` 内对应原文件逐字节相同。
- XSim 兼容副本只把 pool_sample 的 wire 声明初始化拆成 assign，脚本检查整个副本除此以外无变化。
- 顶层六个实例名、51 个不重复编译源、所有路径存在、旧外置存储/适配器模块不在当前清单均通过检查。
- 六个 Control C1 文件的当前哈希与 `build/runs/20261007_213641_808370_cnn_integration/result.json` 一致，本次没有修改 C1。

原包未覆盖回用户压缩文件。旧 partner 存储 wrapper、旧独立仲裁器仅保留在历史文件中，本次没有再改这些历史文件；它们不决定当前板级层次。

## 5. 尚未验证

- 未做全 SoC 综合、BRAM 推断/资源容量核验、布局布线和板级时序闭合。
- 未绑定真实 FPGA 管脚、I/O 电平和晶振；clock_unit 为直通时钟，不带 PLL，不含机械按键去抖。
- 未实测 USB-UART 物理串口、晶振误差和电气连接。
- 未交付完整人脸识别固件或冻结 mailbox 地址；IMEM_INIT_FILE 需实际程序，空参数不能算可运行应用。
- 未验收完整 MobileFaceNet 网络的推理精度、性能或全部算子，仅以原 CNN 小任务验证存储和控制集成。

实现与接线见 [顶层小白说明](../SoC顶层连线与总体IO说明_小白版.md)、[修改说明](CNN实际代码整合修改说明_小白版.md)、[UART 协议](uart_image_bridge_protocol.md)。
