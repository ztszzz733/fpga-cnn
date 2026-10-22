# NEureka 分块卷积＋ReLU 流水试验

本次结果：PASS。来源：`D:\code\FPGA1\cpu_control (2)\cpu_control\build\runs\20261021_225407_neureka_stripes`。真实 NEureka 4×4 PE 阵列、原 ReLU 算子、原四 bank DATASRAM；新增两槽调度模块。没有修改或启用 NVDLA/Vicuna。

## 验证范围

- 主用例：两张 14×11 RGB 测试图，像素 0～127，随机有符号 8 位权重；3×3/stride1/valid 卷积，8 输出通道。每张输出 12×9×8，再执行 ReLU。
- 每 4 行输出为一条带，共 6 个任务。第一条带要 6 行输入；之后每块新增 4 行，保留 2 行真实邻域。输入按 HWC 连续写入，权重与配置预置。
- 输入图片数据不是预加载：仿真驱动通过 DATASRAM IO 接口逐字节写入，首块只在输入+halo 全部提交后派发。不是 UART 时序，也没有 CPU 固件控制。
- 一个 NEureka 与一个独立 ReLU；两块原始卷积结果缓冲交替使用。HWC 逐元素 ReLU 无需格式转换；此结论不扩展到按通道 PReLU 或旧 CHW 池化。
- 每块卷积结果、激活结果逐字节对照 Python 整图整数参考；检查输出/缓冲 guard、输入未被破坏、任务不丢不重、先完成卷积再启动 ReLU。
- 额外用例：顺序对照、13×9/3→5 通道的尾条带+输入停顿、运行中 clear 后复位重启。
- 不是训练好的 MobileFaceNet，不包含真实人脸权重、完整网络、INT8 精度验收、多 NEureka、多实例算子池或 UART 全链路。未验证 stride2/depthwise/7×7。

## 实测结果与时间

| 指标 | 结果 |
|---|---:|
| 主用例检查的最终输出字节数 | 1728 |
| 首次卷积计算阶段开始 | 第 3154 周期 |
| 第一张图输入完成 | 第 6488 周期 |
| 卷积 MATRIXVEC 与 ReLU busy 重叠 | 6990 周期 |
| 计算阶段发生真实输入写入 | 501 个周期 |
| 流水主用例硬件时间 | 19372 周期，193.72 µs @100MHz |
| 同输入节奏顺序对照硬件时间 | 26578 周期，265.78 µs @100MHz |
| 本轮编译 | 261.314 秒 |
| 本轮四项仿真执行合计 | 35.457 秒 |
| 本轮脚本总时间 | 300.073 秒 |

时间不包括之前失败的调试轮次或文档制图。主用例为了展示输入计算重叠，设置了可控的输入间隔；这些周期数不是 UART 吞吐或真实人脸模型性能，不据此承诺加速倍数。

## 波形怎么读

先看 `01_overview.png` 或 `open_01_overview.cmd`，再看 `02_overlap.png` / `open_02_overlap.cmd`，写回细节看 `03_writeback.png`。PNG 来自本次 VCD，不是示意时序；VCD 每个时钟上升沿采样，省略高速时钟轨迹，同根信号在每个视图只出现一次。

- 蓝色：输入；`pixel_eof` 是本试验源每张图片最后一个字节已写入 SRAM 的通知。
- 紫色：NEureka；`core_busy` 包含加载/计算/量化/写回，`compute_active` 仅表示真实 MATRIXVEC 状态，不是每个 PE 的 MAC 有效信号。
- 绿色：ReLU；`post_read_fire`/`post_write_fire` 表示 SRAM 在该拍实际接受读取/写回；`post_addr` 是对应字节地址。
- 红色：并行与全局结果；`compute_post_overlap=1` 表示卷积处于计算阶段同时 ReLU 未完成；`input_compute_overlap=1` 表示输入批次尚在传输时卷积进入计算阶段。
- `conv_done`：卷积完成且存储桥写入已排空。`post_done`：最后一个 ReLU 写响应已返回。后者释放原始结果缓冲。
- `conv_tile`、`post_tile` 是任务号，仅在对应启动/忙/完成时有意义。`slot_states` 每槽占 3 bit：槽 0 在低位，槽 1 在高位；0空闲、1待卷积、2卷积中、3待激活、4激活中。
- `tile_valid && tile_ready` 接受一个输入就绪任务；`tile_ready=0` 时生产者保持任务参数，不覆盖缓冲。最后一块接受后不再接收新任务，需 clear 开始新批次。
- `done` 为本批次全部输出写回后的保持状态，直到 clear/reset；`error` 为锁存错误，存储故障需要系统复位。

## 调度器输入输出约定

| 接口 | 方向和作用 |
|---|---|
| tile_valid / tile_ready | 生产者→调度器 / 调度器→生产者；同时为 1 的上升沿提交任务 |
| tile_slot | 生产者→调度器；选择 0/1 号原始卷积结果缓冲，忙时不会接收 |
| tile_config | 生产者→调度器；SRAM 内 24 字 NEureka 配置块地址 |
| tile_relu_descriptor | 生产者→调度器；原 256 位 ReLU 描述符，包括原始结果地址、最终地址、元素数 |
| tile_last | 生产者→调度器；本批次最后一个任务，仅在握手时采样 |
| cnn_valid / ready / response | CNN→SRAM 请求、SRAM→CNN 接受与返回；客户端 0～8 是卷积数据，9 是配置读取，10 是激活 |
| cnn_addr / wdata / write / byte | CNN→SRAM 的地址、写数据、读写和字节模式 |
| cnn_rdata | SRAM→CNN 的读取结果；各客户端独立返回 |
| accepted_tiles / completed_tiles | 调度器输出；已接收任务数和已经完成最终写回的任务数 |
| conv_start / post_start | 调度器→计算引擎的启动事件，任务号见对应 tile |
| busy / done / error | 调度器输出；批次未完成、批次完成、锁存故障 |
| clear / overlap_enable | 控制输入；中止并清空调度状态 / 允许跨引擎重叠。模式在批次开始前设置并保持 |

权重和配置在任务执行期间不得改变。每个描述符的原始输出地址必须属于选中的 scratch 槽；最终结果、输入、权重与配置不得别名覆盖。当前由生成器保证，尚未加入通用硬件边界校验。

## 实现与下一步

`rtl/neureka/neureka_stripe_pipeline.sv` 是隔离的 CNN 子系统试验入口。原六模块 SoC 入口和顺序任务调度器未改；共享卷积包装层修正了完成条件。调度器信任生产者提供互不冲突的地址和已经就绪的条带；目前没有通用地址检查、循环输入行缓冲、模型任务编译器或 CPU 寄存器入口。

现在验证的是内存交接的条带流水；没有增加卷积到激活的逐像素直连，也没有开启融合 ReLU。独立激活用于验证下一阶段的调度/缓冲交接；之后支持的激活优先评估融合，避免多次 SRAM 访问。

本次同时修正旧 `neureka_conv_engine` 的完成条件：存储桥 idle 时若 HCI 仍有待接收请求，不能提前发 done。首轮小图揭示了最后一笔写回尚未落地的竞态；逐块检查让它在交接时就暴露出来。

后续顺序：固定模型/权重和量化参考 → 验证逐层硬件映射 → CPU 任务描述与图像桥就绪通知 → 跨层条带依赖 → 按带宽决定是否复制卷积单元。

## 复现

在 WSL 的工程目录运行 `python3 scripts/run_neureka_stripes.py`；已有匹配程序时加 `--reuse`，源码哈希不匹配会拒绝复用。每次产生新的 build/runs 目录。Windows Python 运行 `scripts/prepare_neureka_stripes.py <运行目录>` 生成本交付。
