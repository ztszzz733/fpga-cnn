# 两张真实人脸小区域：跨层条带流水验证

后续进展（2026-10-22）：已增加两套真实NEureka的空闲实例自动派发，见 [双实例验证](../mobilefacenet_dual/README.md)。本页保留单实例条带流水阶段结果。

本轮结果：**PASS**。来源 `D:\code\FPGA1\cpu_control (2)\cpu_control\build\runs\20261022_000428_mobilefacenet_pipeline`。一套真实NEureka、一套量化后处理、两个INT32临时槽，自动按依赖表调度两张图片的三层局部网络。顶层六模块划分不变，尚未接生产CPU/UART。

## 验证了什么

- 输入为用户的 `person_1.jpg`、`person_2.jpg`，权重与上一轮固定MobileFaceNet相同；两图使用相同量化尺度。计算空间范围仍是首层6×6×64→DW4×4×64→PW4×4×64，全部64个通道参与。
- 每条带两行，14个任务，28次NEureka卷积发射与14次量化后处理。每个任务都携带frame/layer/stripe标签。
- 3×3 DW条带需要其上游4行，依赖相邻两个已写完的首层条带；1×1 PW只需要对应DW条带。依赖满足后才可发射。
- 两个32位临时槽复用：直到量化的最后写响应完成才释放。量化后的各层/各帧特征区仍单独保留，尚未实现循环行缓冲或全模型内存分配。
- 后层读取前层真实硬件输出，Python只提供初始输入/权重/参数和检查用金标准，没有给硬件注入中间结果。

并行、顺序、反压加中途清除复位三项都通过。每项核对 **43,520 字节**（包含全部条带INT32卷积和UINT8量化输出），所有最终输出文件哈希相同；检查不可写区域不变、任务不重不丢、标签正确、槽不被提前复用、halo依赖和clear后的重启。

## 并行证据

| 指标 | 实测 |
|---|---:|
| 卷积计算阶段与后处理busy重叠 | 22,453 周期 |
| 卷积计算阶段内，后处理发生写握手 | 3,237 周期 |
| 顺序对照的计算/后处理重叠 | 0 周期 |
| 第二张图首次卷积启动 | 第 13,704 周期 |
| 第一张图最后条带写完 | 第 112,695 周期 |

一次跨层交接发生在第 **55017 周期**：frame 0、layer 1、stripe 0 已启动，此时同帧上一层仍有任务 [4] 未全部写完。它所必需的条带已经提交，测试平台在发射时单独核验依赖。

只有一套NEureka，各层卷积仍轮流使用它；并行的是卷积与后处理。`core_state=4`表示计算阶段，不代表所有PE每拍都有效乘加；上表结合实际写握手和逐字节结果证明有用的重叠。

## 波形与信号

- [全程：两帧交错与条带状态](01_overview.png)
- [细节：计算阶段与量化读写重叠](02_overlap.png)
- [细节：前层未全部结束，后层已启动](03_layer_handoff.png)
- GTKWave打开入口：`open_01_overview.cmd`、`open_02_overlap.cmd`、`open_03_layer_handoff.cmd`。
- [周期事件表](events.csv)、[任务依赖/地址/量化尺度](workload.json)、[完整测试结果](result.json)。

每个视图内信号只出现一次，按模块分组着色；紫色卷积、绿色后处理、棕色调度/状态。PNG由本次真实VCD绘制，波形在每个时钟上升沿采样，不包含完整PE内部海量信号。

| 信号 | 从哪里到哪里 / 如何看 |
|---|---|
| conv_frame/layer/stripe，post_frame/layer/stripe | 调度表→相应执行单元的任务标签；frame0/1对应两张图片，layer0首层、1深度卷积、2点卷积。闲置期间保留/选择的标签不表示任务正在执行，须结合start/busy。 |
| conv_start | 调度器→NEureka封装，每条带两次（两个32通道组） |
| conv_node，post_node | 调度器→观察端，当前任务表编号 |
| conv_slot，post_slot | 调度器→执行端，正在使用的临时缓冲槽0或1；并发时必须不同 |
| core_busy，compute_active | NEureka→观察端，分别为核心忙、忙且处于MATRIXVEC计算阶段 |
| conv_read_fire / conv_write_fire | NEureka存储桥↔DATASRAM，有读取/写入请求得到接受；配置端口另行读取，不计在这两个信号里 |
| conv_tile_done | 卷积封装→调度器，两个通道组及待写事务完成，条带可开始后处理，但槽尚不能释放 |
| post_start / post_busy | 调度器→后处理、后处理→观察端，参数加载和重定量过程 |
| post_read_fire | 后处理→DATASRAM读握手，既包括参数，也包括32位卷积结果 |
| post_write_fire / post_address | 后处理→DATASRAM写握手和地址，每次提交一个UINT8结果 |
| post_done | 后处理→调度器，最后一次写响应完成；设置完成位并释放槽 |
| compute_post_overlap | 观察逻辑，compute_active与post_busy同时为1 |
| completed_mask | 调度器→观察端，十六进制显示；bit i为1表示任务i的量化结果已写完 |
| slot_states | 调度器→观察端，slot1为高3位、slot0为低3位；0空闲、1待卷积、2卷积中、3待后处理、4后处理中。显示的是打包数值，不是单个状态码。 |
| done / error / memory_fault | 整批结束、执行错误、SRAM访问错误；通过用例两种错误全程为0 |

没有UART输入波形，因为这次图像是SRAM预加载。看到卷积读取请求，表示从SRAM取数据，不等于串口正在接收图片。

## 时间与对照

| 模式 | 100MHz硬件周期 | 对应硬件时间 | 电脑实际仿真时间 |
|---|---:|---:|---:|
| 条带并行 | 115,900 | 1159.00 µs | 59.00 秒 |
| 同一任务图顺序执行 | 147,932 | 1479.32 µs | 55.99 秒 |
| 反压+中途清除后重启 | 129,286 | 1292.86 µs | 50.12 秒 |

本次首次编译 **271.90秒**，整个运行脚本总耗时 **438.23秒**。复位重启用例的周期数统计重启后的完整任务，电脑耗时还包含被中断的预热段。100MHz是仿真设定，没有通过综合证明最高频率。

顺序/并行周期比为 **1.276**。它只比较同一小区域、同一条带任务图是否允许重叠，不是完整网络、人脸识别或UART端到端性能承诺，也不是与前一版整层任务划分的直接性能比较。

## 文件、复现与下一步

设计说明见 [调度与缓冲约定](../../docs/mobilefacenet_pipeline_design.md)，数值格式沿用 [整数约定](../../docs/mobilefacenet_quant_contract.md)。新模块在 `rtl/cnn_quant/quant_stripe_scheduler.sv`；原顺序小链条和上一轮小例保留。

Windows生成数据：`scripts/gen_mobilefacenet_pipeline.py build/mobilefacenet_pipeline_data`。WSL运行已有匹配程序：`python3 scripts/run_mobilefacenet_pipeline.py --reuse --data build/mobilefacenet_pipeline_data`。只在RTL/监视器改变时去掉`--reuse`重新编译；输入/参数变化仍要生成新的金标准。每次保存独立运行目录，缓存为 `.neureka_pipeline_build`。

下一步再接分批输入的行就绪通知和输入缓冲回收，然后扩展更长网络的残差依赖。CPU命令提交、UART流式输入、循环行缓冲、完整量化校准、GDConv7×7硬件、全网络推理和多NEureka仍未完成。内部预取沿用关闭配置；本次没有修复第三方预取问题，也未使用GPU。
