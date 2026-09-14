# 模块接口与独立仿真

完整代码在本目录对应链接中。全部时序模块用同一个时钟，上升沿采样；`rst_n` 为低有效异步复位，`clear` 为同步清除。scratchpad 故意不整块复位，先填入数据后才允许有效计算。

在工程根目录运行 `python mobilefacenet/scripts/run_tests.py 测试名称`。以下模块均已有实际通过的自检查 testbench；基础模块可以由一个联合 testbench 分别实例化，覆盖其接口和边界行为。出现 `$fatal` 或缺少 PASS 标记都算失败。

## 1. 寄存器

代码：[accelerator_regs.sv](../rtl/accelerator_regs.sv)；测试：[tb_accelerator_regs.sv](../tb/tb_accelerator_regs.sv)。

输入 `clk/rst_n`、32 位 `mmio_addr/mmio_wdata`、`mmio_we/mmio_re`；输出 32 位 `mmio_rdata`、`mmio_ready`。后端输入 `accelerator_busy/done/error`；输出单周期 `accelerator_start/reset`、4 位 `op_type`，以及七个 32 位配置值。DONE / ERROR 由寄存器模块保持，配置写锁覆盖启动交接周期。

测试数据与预期：复位 FEATURE_SIZE=0x00700070、CHANNELS=0x00010003；逐个配置寄存器写入并读回 `0x12340000+寄存器索引`；STATUS 写入无效；CONTROL 写 13 启动 ADD，OP_TYPE=3。忙时重复 START 不再启动、STATUS=5，原任务完成后 STATUS=6；RESET 清状态并保留 OP_TYPE；非法/未对齐 MMIO 不返回 ready。

## 2. MAC 与累加器

代码：[mac_unit.sv](../rtl/mac_unit.sv)、[accumulator.sv](../rtl/accumulator.sv)；联合测试：[tb_mac_unit.sv](../tb/tb_mac_unit.sv)。

MAC 是组合逻辑，输入两个 signed 8 位数据，输出符号扩展后的 signed 32 位乘积。累加器输入 `clear/load_bias/enable`、signed 32 位 `bias/product`，输出 `value`；优先级为 reset > clear > load_bias > enable。

穷举 256×256 个输入对，包括 `-128×-128=16384`、`-128×127=-16256`。时序检查：bias=-10，加入 -3×4 后为 -22；enable=0 保持 -22；0x7fffffff 加 1 得到 0x80000000；clear 后为 0。

## 3. 普通卷积引擎与 1×1

代码：[conv_engine.sv](../rtl/conv_engine.sv)；测试：[tb_conv_engine.sv](../tb/tb_conv_engine.sv)、[tb_conv1x1.sv](../tb/tb_conv1x1.sv)。

`start` 接收一个输出点任务：4 位 kernel、16 位 input_channels、32 位 bias。随后只在 `sample_valid && sample_ready` 的上升沿接收 INT8 输入/权重对。收到 K²×CI 对后 `done` 脉冲置 1、`busy` 置 0，32 位 `result` 保持到清除或下一次任务。输入通道/空间地址由独立地址模块负责，engine 不访问 RAM。

3×3 测试 CI=2、3，以 `input=i-9`、`weight=i%5-2`、bias=-5，结果与 testbench 中的整数求和比较，每三项插入两个空闲周期，检查没有提前完成。K=7 被普通引擎拒绝。1×1 测试 CI=1、3、16，使用同一硬件，验证收到 CI 项便完成。

## 4. Depthwise 引擎

代码：[depthwise_conv_engine.sv](../rtl/depthwise_conv_engine.sv)；测试：[tb_depthwise_conv_engine.sv](../tb/tb_depthwise_conv_engine.sv)。

接口与普通引擎相似，但没有 input_channels 参数，每个任务严格接收 K² 对。当前 channel 的选择由地址生成器控制。每次 start 都重新加载该 channel 的 bias，不包含其他 channel 的累加结果。

连续运行：K3、input=2、weight=3、bias=1，得到 55；下一 channel input=-4、weight=2、bias=-7，得到 -79；K7、input=weight=-128、bias=0，得到 802816。每项之间插入空闲周期；K1 被拒绝。整层测试再用各通道不同常量验证 DW 地址没有串通道。

## 5. 激活、残差、量化

| 模块与代码 | 接口 | Testbench | 明确预期 |
|---|---|---|---|
| [relu6_unit](../rtl/relu6_unit.sv) | signed INT32 `value/result`，`relu_enable/relu6_enable`，参数 RELU6_MAX | [tb_relu6_unit](../tb/tb_relu6_unit.sv) | 默认上限 96；负数→0，95→95，97→96；仅 ReLU 时正数不截到 96 |
| [add_unit](../rtl/add_unit.sv) | 两个 signed INT8 输入，signed INT32 输出 | [tb_add_unit](../tb/tb_add_unit.sv) | 穷举全部输入对，-128+-128=-256，127+127=254；本模块不提前饱和 |
| [quantizer](../rtl/quantizer.sv) | signed INT32 value、8 位 shift，输出 signed INT32 shifted 与饱和 INT8 result | [tb_quantizer](../tb/tb_quantizer.sv) | -3>>>1=-2；-256>>>1=-128；254>>>1=127；越界饱和；覆盖 shift=31/255 |

顶层先使用 quantizer 的 `shifted` 输出，在 INT32 域激活后，再用 shift=0 的 quantizer 饱和输出。ReLU6 上限在最终整数域解释，避免把“实数 6”直接当成所有层共同的 INT32 累加上限。

## 6. 地址生成

代码：[address_generator.sv](../rtl/address_generator.sv)；测试：[tb_address_generator.sv](../tb/tb_address_generator.sv)。

输入四个基地址、FEATURE_SIZE、CHANNELS、LAYER_PARAM、OP_TYPE，以及 `output_x/y`、`element_index`、`input_channel/output_channel`、`tap`。输出输入/权重/Bias/输出/ADD 第二输入的字节地址，输出宽高与元素数、`input_is_padding`、`config_valid`。

```text
iy = output_y*stride + tap/kernel - padding
ix = output_x*stride + tap%kernel - padding
input = INPUT_ADDR + ((channel*height + iy)*width + ix)
normal_weight = WEIGHT_ADDR + ((oc*CI + ic)*K*K + tap)
dw_weight = WEIGHT_ADDR + (oc*K*K + tap)
bias = BIAS_ADDR + oc*4
output = OUTPUT_ADDR + ((oc*OH + output_y)*OW + output_x)
```

普通模式 channel=ic，DW 模式 channel=oc。点运算使用各基地址+element_index。计算值不会直接当成对齐 RAM 地址，Memory IF 负责对齐和字节选择。

明确测试：W=H=5、CI=2、CO=3、K3/S1/P1，基地址 input=0x101、weight=0x2003、bias=0x3000、output=0x1001；ic=1、oc=2、x=1、y=2、tap=4，期望输入=0x125、权重=0x2034、Bias=0x3008、输出=0x103e。另测左上 padding、DW7 最后一个 tap、ADD 连续地址、FINAL 长度128，以及溢出/重叠/非法参数。

## 7. 缓冲

代码：[sample_buffer](../rtl/sample_buffer.sv)、[input_buffer](../rtl/input_buffer.sv)、[weight_buffer](../rtl/weight_buffer.sv)、[bias_buffer](../rtl/bias_buffer.sv)、[output_buffer](../rtl/output_buffer.sv)；联合测试：[tb_buffers.sv](../tb/tb_buffers.sv)。

Input / Weight 都是 sample_buffer 包装：`we`、独立 `waddr/raddr`、signed INT8 `wdata/rdata`。默认 DEPTH=49、ADDR_WIDTH=6，上升沿写、组合读；无效读地址返回 0，无效写地址不写入。Bias / Output 是带 clear 和 we 的单值寄存器，分别 32 / 8 位。

测试 49 个索引依次写入 `-120+5*i`，逐项读回；最后一个值120；Bias=-1234567；越界索引63读0；clear 后标量缓冲为0。将来改成同步 BRAM 时须同时调整控制器的读延迟，不能仅替换存储声明。

## 8. Memory IF

代码：[accelerator_mem_if.sv](../rtl/accelerator_mem_if.sv)；测试：[tb_accelerator_mem_if.sv](../tb/tb_accelerator_mem_if.sv)；带等待 RAM 模型：[model_data_ram.sv](../tb/model_data_ram.sv)。

内部请求用 `cmd_valid/cmd_ready` 握手，`cmd_write` 选择写，`cmd_byte` 选择 INT8 或整字访问；`cmd_addr/wdata` 32 位。一次请求完成后返回单周期 `rsp_valid` 和 32 位 `rsp_rdata`，`idle` 表示没有外部事务。控制器在等待状态始终能接收 response，所以没有 rsp_ready。

外部接口严格保持请求直到 mem_ready。`cancel` 不撤回已呈现请求，排空后丢弃 response；如果取消发生在 INT8 写的读阶段，不再进入写阶段；已进入写阶段则让写完成。

输入 RAM 字节 `00 7f 80 ff`，整字读0xff807f00，四路字节读分别0、127、-128、-1。地址4初值0x11223344，在地址5写0xa5后得到0x1122a544，其他字节不变。四个位置依次写 `11 80 fe 7f`，整字得到0x7ffe8011。测试固定5周期等待、取消读、取消读改写、取消已提交写；RAM 模型检查等待期间地址/数据/读写选择稳定。

## 9. 算子控制器

代码：[mobilefacenet_controller.sv](../rtl/mobilefacenet_controller.sv)；测试：[tb_mobilefacenet_controller.sv](../tb/tb_mobilefacenet_controller.sv)。

输入配置与 start/reset，输出锁存配置给地址与数据通路；接收地址合法性、padding、输出尺寸、Memory IF ready/response、engine ready/done/error。输出 memory command、地址选择、各缓冲写使能、engine_start/sample_valid、坐标/通道/tap 计数和 busy/done/error。

状态编号用于波形显示：

| 编号 | 状态 | 编号 | 状态 |
|---|---|---|---|
| 0 | IDLE | 10 | WAIT_ENGINE |
| 1 | LOAD_CONFIG | 11 | READ_A |
| 2 | LOAD_BIAS | 12 | WAIT_A |
| 3 | WAIT_BIAS | 13 | READ_B |
| 4 | ENGINE_START | 14 | WAIT_B |
| 5 | LOAD_INPUT | 15 | POST |
| 6 | WAIT_INPUT | 16 | WRITE_BACK |
| 7 | LOAD_WEIGHT | 17 | WAIT_WRITE |
| 8 | WAIT_WEIGHT | 18 | DONE |
| 9 | CONV（普通/DW 共用馈数状态） | 19 | ERROR |

每个输出点重复“装 bias→装窗口/权重→馈数→后处理→写回”。LOAD_CONFIG 验证失败直接 ERROR，不碰 RAM。DONE / ERROR 状态向寄存器发脉冲，下一周期回 IDLE；MMIO 的 sticky 位在该交接沿置位。

独立测试将输出数固定为4，Memory command_ready 和 engine_ready 插入不同周期阻塞，response延迟2周期。NORMAL 期望72个采样/144个内部RAM命令/4次引擎启动；DW 为36/76/4；RELU6、COPY、FINAL 为0/8/0；ADD 为0/12/0。检查锁存配置、非法配置零RAM访问、RESET 取消。

## 10. 顶层与整层验证

代码：[mobilefacenet_accelerator_top.sv](../rtl/mobilefacenet_accelerator_top.sv)；测试：[tb_top_smoke.sv](../tb/tb_top_smoke.sv)、[tb_mobilefacenet.sv](../tb/tb_mobilefacenet.sv)。

顶层只暴露 clk/rst_n、用户指定的 MMIO 与 Memory Master 两组接口。参数 BASE_ADDR 默认0x40000000、RELU6_MAX 默认96。所有调试信号位于内部，不增加外部寄存器。

Smoke：3×3输入1…9、权重全1、bias=0，输出45（0x2d），写入非对齐输出字节，保留邻接 RAM 数据。整层 testbench 读取 Python 生成的任务表，模拟外部 MMIO 配置，不包含 CPU 指令模型。

完整逐层测试数据由 [generate_vectors.py](../scripts/generate_vectors.py) 固定随机种子生成，原始 RAM、各层参数、输出 shape、期望值均在 `build/vectors/`。检查方法与结果见 [verification.md](verification.md)。
