# 分阶段开发与测试

完整代码均在下表链接的文件内。开发顺序遵循“实现 → 独立 Testbench → 实际仿真通过 → 下一阶段”，最后连接顶层和软件 Golden 对比。最终回归会再运行所有阶段。所有时序模块在上升沿工作；`rst_n` 低有效，`clear` 高有效同步清零。

## 1–2. accelerator_regs 与 MMIO Testbench

- 代码：[accelerator_regs.v](../rtl/accelerator_regs.v)
- Testbench：[tb_accelerator_regs.sv](../tb/tb_accelerator_regs.sv)
- 运行：`python scripts/run_tests.py accelerator_regs`
- MMIO 端口与九个地址详见[接口说明](architecture.md#2-九个-mmio-寄存器)。额外内部接口为单周期 `accelerator_start/accelerator_reset` 输出，`accelerator_busy/done/error` 状态输入，以及 7 个 32 位配置输出。
- 时序：配置同步写、组合读；外部状态完成事件保存到粘滞位。RESET 高于 START；复位脉冲期间忽略旧 DONE/ERROR。

| 测试数据 / 操作 | 预期 |
|---|---|
| 复位后读取 IMAGE_SIZE / CHANNELS / CNN_PARAM | `00E000E0` / `00010003` / `00100113` |
| 配置地址索引 i=2…8 写入 `12340000+i` | 全部原值读回 |
| CONTROL 写 1 | START 恰好一周期 |
| BUSY 时改 INPUT_ADDR | 应答但值不变 |
| BUSY 时再次 START | 不启动，STATUS=5 |
| 随后 DONE，BUSY 下降 | STATUS=6，持续保持 |
| CONTROL 写 3 | 仅 RESET 脉冲，状态清零 |
| RESET 脉冲期间旧 DONE/ERROR 到来 | 不重新置位状态 |
| 写 STATUS、访问 CONTROL 保留位 | STATUS 写无效，CONTROL 读零 |
| 越界地址 / 非对齐地址 / 错误基址 | ready=0，读数据为零 |

通过标记：`PASS tb_accelerator_regs`。

## 3. ReLU

- 代码：[relu_unit.v](../rtl/relu_unit.v)
- Testbench：[tb_relu_unit.sv](../tb/tb_relu_unit.sv)
- 组合接口：signed `[31:0] value`，1 位 `enable` → signed `[31:0] result`。
- 数据 / 预期：启用时 `-9→0`、`0→0`、`123→123`、INT32_MIN→0、INT32_MAX→INT32_MAX；禁用时负数和 INT32_MIN 原样透传。
- 运行：`python scripts/run_tests.py relu_unit`；通过标记：`PASS tb_relu_unit`。

## 4. Quantizer

- 代码：[quantizer.v](../rtl/quantizer.v)
- Testbench：[tb_quantizer.sv](../tb/tb_quantizer.sv)
- 组合接口：signed `[31:0] value`、`[7:0] quant_shift`、1 位 `relu_enable` → signed `[7:0] result`。

| value | shift | ReLU | 预期 result |
|---:|---:|---:|---:|
| 127 | 0 | 0 | 127 |
| 128 | 0 | 0 | 127 |
| -128 | 0 | 0 | -128 |
| -129 | 0 | 0 | -128 |
| -1 | 0 | 1 | 0 |
| 255 | 1 | 1 | 127 |
| -3 | 1 | 0 | -2 |
| 2147483647 | 31 | 0 | 0 |
| -2147483648 | 31 | 0 | -1 |
| -1 | 255 | 0 | -1 |
| 17 | 255 | 1 | 0 |

运行：`python scripts/run_tests.py quantizer`；通过标记：`PASS tb_quantizer`。

## 5. MAC 和 Accumulator

- 代码：[mac_unit.v](../rtl/mac_unit.v)、[accumulator.v](../rtl/accumulator.v)
- Testbench：[tb_mac_unit.sv](../tb/tb_mac_unit.sv)
- MAC 组合接口：signed INT8 `input_value,weight_value` → signed INT32 `product`。
- 累加器接口：`clk,rst_n,clear,load_bias,enable`，signed INT32 `bias,product` → 寄存的 signed INT32 `value`。
- 优先级：硬复位 → clear → load_bias → enable；没有使能时保持。
- 穷举输入和权重各 -128…127：全部 65,536 种乘积与 Testbench 整数乘法一致。
- 顺序验证：Bias=-10、输入=-3、权重=4，下一累加结果=-22；停止使能保持 -22；INT32_MAX+1 得到 INT32_MIN；clear 得到 0。
- 运行：`python scripts/run_tests.py mac_unit`；通过标记：`PASS tb_mac_unit`。

## 6. MaxPool

- 代码：[maxpool_unit.v](../rtl/maxpool_unit.v)
- Testbench：[tb_maxpool_unit.sv](../tb/tb_maxpool_unit.sv)
- 接口：`clk,rst_n,clear,valid,first`，signed INT32 `value` → 寄存的 signed INT32 `result`。
- 每组第一笔 `valid=1,first=1` 直接装入；随后 `first=0` 做最大值。Controller 保证一组四笔；模块本身允许任意长度流，且用单笔即可旁路。
- 数据 / 预期：`[-9,-3,-20,-4]→-3`；下一组 `[2,99,99,8]→99`；INT32_MIN 和 INT32_MAX 比较正确；没有 valid 保持结果；clear 清零。
- 运行：`python scripts/run_tests.py maxpool_unit`；通过标记：`PASS tb_maxpool_unit`。

## 7. Buffers

| 模块 / 完整代码 | 接口 | 行为 |
|---|---|---|
| [sample_buffer](../rtl/sample_buffer.v) | `clk,we,waddr,raddr,wdata,rdata`；参数 WIDTH、DEPTH、ADDR_WIDTH | 同步写、异步读；读越界返回零，写越界忽略 |
| [input_buffer](../rtl/input_buffer.v) | 同上，signed INT8；默认 DEPTH=9，ADDR_WIDTH=4 | 一个 IC 的 3×3 窗口 |
| [weight_buffer](../rtl/weight_buffer.v) | 同上，signed INT8；默认 DEPTH=9，ADDR_WIDTH=4 | 对应 9 个权重 |
| [bias_buffer](../rtl/bias_buffer.v) | `clk,rst_n,clear,we`，signed INT32 `wdata/rdata` | 单个 Bias 寄存器 |
| [output_buffer](../rtl/output_buffer.v) | `clk,rst_n,clear,we`，signed INT8 `wdata/rdata` | 写回前结果寄存器 |

深度参数变更时，调用方需保证 `2^ADDR_WIDTH >= DEPTH`。Scratchpad 不清空存储数组：Controller 每次使用前写满 9 项，含显式 padding 零。Bias 和 Output Buffer 复位清零。

Testbench：[tb_buffers.sv](../tb/tb_buffers.sv)。向索引 i=0…8 写入 `-128+29*i`，逐项读出必须匹配；Bias 写 -1234567，Output 最终为 104；索引 15 返回 0；标量 clear 后为零。

运行：`python scripts/run_tests.py buffers`；通过标记：`PASS tb_buffers`。

## 8. Address Generator

- 代码：[address_generator.v](../rtl/address_generator.v)
- Testbench：[tb_address_generator.sv](../tb/tb_address_generator.sv)
- 配置输入：4 个 32 位 base、IMAGE_SIZE、CHANNELS、CNN_PARAM。
- 坐标输入：32 位 `output_x/output_y`，16 位 `input_channel/output_channel`，4 位 `tap`（0–8），2 位 `pool_sample`（0–3）。
- 输出：4 个 32 位字节地址，1 位 `input_is_padding/config_valid`，32 位卷积 / 最终宽高。
- 全组合；所有空间寻址和尺寸 / 区域检查在该模块完成。

| 测试配置 / 坐标 | 预期 |
|---|---|
| 5×5、IC=3、OC=2、stride=1、pad=1 | CW=CH=OW=OH=5 |
| 输出(0,0)、tap=0 | padding=1，不访问输入 RAM |
| bases=1001/8001/4003/6000，tap=4、IC索引2、OC索引1 | input=1003，weight=402C，bias=6004，output=8002 |
| 输出(4,4)、tap=8 | padding=1 |
| stride=2、pad=0、Pool=1、pool_sample=3、tap=0 | CW=CH=2，OW=OH=1，input=1027 |
| 224×224、有效分离输出地址 | 合法，尺寸未写死 |
| 零尺寸 / 通道 / stride、kernel=4、保留位、Bias不对齐 | config_valid=0 |
| 区域越界 / 输出与只读数据重叠 / 空池化 | config_valid=0 |
| 单字节输出首地址 FFFFFFFF | 合法，不误报边界溢出 |

运行：`python scripts/run_tests.py address_generator`；通过标记：`PASS tb_address_generator`。

## 9. Memory Interface

- 代码：[accelerator_mem_if.v](../rtl/accelerator_mem_if.v)
- Testbench：[tb_accelerator_mem_if.sv](../tb/tb_accelerator_mem_if.sv)
- RAM 模型：[model_data_ram.sv](../tb/model_data_ram.sv)，仅仿真使用。
- 内部命令：`cmd_valid/cmd_ready` 握手；`cmd_write` 选读写，`cmd_byte` 选 INT8 / INT32，32 位 `cmd_addr/cmd_wdata`。INT32 内部请求应对齐；INT8 写使用低 8 位。
- 内部响应：`rsp_valid` 单周期，32 位 `rsp_rdata`；读字节自动符号扩展，写响应数据为零；无 rsp_ready，消费方必须接收。
- `cancel` 取消计算相关命令，已呈现外部的传输需排空；`idle` 表示接口没有活动请求。
- 外部端口与协议见[RAM 握手](architecture.md#3-ram-布局与地址)。

| RAM 初值 / 操作 | 预期 |
|---|---|
| word[0]=FF807F00，按字读取 | FF807F00 |
| 分别读地址 0、1、2、3 字节 | 0、127、-128、-1，全部扩展到 INT32 |
| word[4]=11223344，向字节地址5写A5 | word[4]=1122A544 |
| 向地址8写完整字 DEADBEEF | 原值读回 |
| 字节写在 RMW 读阶段取消 | 不执行写阶段，原值保留 |
| 读取消 | 不产生内部响应 |
| 已呈现的整字写 / 字节写在等待中取消 | 写请求稳定保持并完成，不返回响应 |

RAM 模型检查任意等待周期内地址 / 数据 / 读写信号不变、地址对齐、不越界、读写互斥。此阶段 WAIT_CYCLES=5，顶层完整测试=3，顶层 smoke=0。

运行：`python scripts/run_tests.py accelerator_mem_if`；通过标记：`PASS tb_accelerator_mem_if`。

## 10. Controller FSM

- 代码：[cnn_controller.v](../rtl/cnn_controller.v)
- Testbench：[tb_cnn_controller.sv](../tb/tb_cnn_controller.sv)
- 配置输入 / 快照输出：7 个 32 位寄存器，`start` 接收时锁存。
- 控制输入：`soft_reset,start,config_valid,input_is_padding,mem_idle,cmd_ready,rsp_valid`，以及最终 `output_width/output_height`。
- 状态输出：`busy,done,error`；DONE/ERROR 为 FSM 事件，由 MMIO 模块保持。
- 命令输出：`cmd_valid,cmd_write,cmd_byte,address_select`；选择值 0=输入，1=权重，2=Bias，3=输出。
- 数据通路输出：`datapath_clear,input_we,weight_we,bias_we,accumulator_load,mac_enable,input_zero,pool_first,pool_valid,output_we`。
- 循环坐标输出：`output_x/y,input_channel,output_channel,tap,pool_sample`；5 位 `debug_state` 仅供内部验证，未暴露到顶层。

独立仿真用模拟命令接收方提供周期性背压和延迟响应，不依赖实际数据通路。固定最终 2×1、OC=2、IC=2，并将每个窗口的 tap0 模拟为 padding：

| 模式 | 卷积数 / Bias读次数 | MAC 次数 | Pool 输入次数 | 输出数 | 内部命令数 |
|---|---:|---:|---:|---:|---:|
| Pool 开启 | 16 | 288 | 16 | 4 | 564 |
| Pool 关闭 | 4 | 72 | 4 | 4 | 144 |

运行中改变外部 CNN_PARAM 不影响快照；非法参数不产生 RAM 命令；软复位清除忙和控制使能；DONE 后回到 IDLE。

运行：`python scripts/run_tests.py cnn_controller`；通过标记：`PASS tb_cnn_controller`。

## 11. 顶层连接与首次端到端测试

- 代码：[cnn_accelerator_top.v](../rtl/cnn_accelerator_top.v)
- Testbench：[tb_top_smoke.sv](../tb/tb_top_smoke.sv)
- RAM 输入地址 0x100 存 `1,2,3,4,5,6,7,8,9`；权重地址 0x200 存九个 1；Bias 地址 0x300 存 INT32 零。
- MMIO 配置 3×3、IC=OC=1、stride=1、pad=0、shift=0、ReLU/Pool 关闭；输出地址 0x401。
- 写 START → BUSY=1 → 自动读 / 计算 / 写回 → STATUS=2。
- 预期输出 `1+2+…+9=45`（0x2D），0x400 和 0x402 的初始哨兵 A5 不变。
- 运行：`python scripts/run_tests.py top_smoke`；通过标记：`PASS tb_top_smoke`。

## 12. 完整 Testbench 和软件 Golden Result

- Testbench：[tb_cnn_accelerator.sv](../tb/tb_cnn_accelerator.sv)
- 软件计算：[generate_vectors.py](../scripts/generate_vectors.py)，Python 大整数求和 → 显式 INT32 回绕 → ReLU → Pool → shift → saturate；不读取 RTL 内部计算结果。
- RAM 输入 / 权重 / Bias / 输出地址：`0x101 / 0x30003 / 0x31000 / 0x32001`，特意覆盖不对齐的激活和权重访问。
- `build/vectors/manifest.json` 给出每例完整参数、输出尺寸、长度和前 16 个有符号预期值；`.memh` 是预装 RAM 测试数据，`.golden.hex` 是逐字节预期输出。
- 确定性随机种子：20260911。每次运行重新生成同一组数据。

覆盖：手算 45、RGB 多输出通道、ReLU 饱和、全负数 Pool、stride=2 与 Pool、padding=2、shift=255、INT32 回绕、奇数边界丢弃、6 个随机组合、完整 224×224 RGB。随后检查 9 个非法配置、等待期间软复位、无需硬复位的再次启动。

预期特殊输出：`sanity=[45]`；`shift_255=[0,-1]`；`int32_wrap=[-128,127]`。其余所有输出与独立 Golden 文件逐字节比较。

每个有效运行必须：启动时 STATUS=1，完成 STATUS=2，精确写回 nout 个字节、输出范围外整个 RAM 完全不变、DONE 保持且不自动重复启动。非法配置必须 STATUS=4 且零 RAM 访问；RESET 排空后 STATUS=0 并停止新请求。

运行：`python scripts/run_tests.py cnn_accelerator`。通过标记：`PASS tb_cnn_accelerator`。完成编译后可用 `vvp build/tb_cnn_accelerator.vvp +vcd` 生成 `build/cnn.vcd`；完整 224 用例波形很大，通常先看 smoke 的信号或缩小用例。
