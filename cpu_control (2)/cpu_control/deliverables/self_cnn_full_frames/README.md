# 完整 MobileFaceNet：四图地址驱动并行 / 流水验证

本报告只使用已完成的真实 RTL 运行 `20261023_180539_292440_self_full`，场景 `overlap`。CNN 接收一份固定流程模板与四组图片/工作区地址，自主展开 **131 步/图、524 个任务**，所有卷积、后处理、残差 Add、调度及 bai 四 bank SRAM 均执行实际 RTL。

四图最终结果均经实际 SRAM IO 口读取并与独立整数参考逐字节一致，总用时 **1,138,093,351 拍**，计算完成于 1,138,093,244 拍。本次完整运行没有同数据、同配置的串行场景，未给出串行加速倍数。

仅按 **100 MHz** 换算，该批四图为 **11.38093 秒**，批次吞吐 **0.3515 图/秒**；这是频率假设下的周期换算，100 MHz 尚未通过此完整配置的布局布线时序验证。均摊时间 2.84523 秒/图不等于首图延迟。主机仿真计算耗时 43.68 分钟，包含初始化与收尾的运行器耗时为 43.83 分钟。

## 输入、重叠与流水

- [四张输入图](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/input_images.png>)：合成测试 RGB，完整输入形状 `[112, 112, 3]`。
- [四图流水总览](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/frame_pipeline.png>)、[每个步骤的甘特图](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/all_steps_gantt.png>)。
- [算子 active/work/wait](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/operator_cycles.png>)、[全部任务事件表](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/task_events.csv>)、[逐层事件汇总](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/layer_events.csv>)。
- [MAC 同拍采样图](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/mac_detail.png>)、[跨类同拍采样图](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/pipeline_detail.png>)；对应 `open_mac_detail.cmd` / `open_pipeline_detail.cmd` 可打开真实 VCD 的 GTKWave 会话，每个会话10根物理信号各出现一次。窗口相对时间不代表网络从零开始，窗口外没有记录，不推断为RTL未知。
- [可编辑架构图](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/architecture.drawio>)：完整入口配置 `MAX_TASKS=1024`、模板容量256、SRAM 16 MiB；此前短流程默认64任务的配置不能直接装下本次524任务。

最多 4 图同时有在途任务。跨图真实 MAC / 接受写回重叠 82,088,133 拍，跨算子类型真实工作重叠 24,732,963 拍；后续图输入期间已有图 MAC 推进 1,269,827 拍。单纯多图 busy 为 1,135,900,593 拍，未将其等同于实际运算重叠。

| frame | 图像提交 | 首步启动 | 结果读取确认 |
|---:|---:|---:|---:|
| 100 | 762,048 | 762,422 | 1,136,923,263 |
| 101 | 1,524,097 | 1,524,319 | 1,137,187,359 |
| 102 | 2,286,208 | 2,286,216 | 1,137,451,453 |
| 103 | 3,048,416 | 3,048,637 | 1,138,093,349 |

任务条跨度来自实际 launch→done，包含算子内部装载、计算和写回等待。每张图内部按固定顺序执行；流水发生在不同图片、不同算子之间，不声称同一层按行输出直接流入下一层。

## 本次完整运行的性能限制

当前瓶颈指向 **1×1 算子池**：2 个实例平均忙碌率 97.81%，同时该类算子有最多的同类资源等待 2,016,986,427 帧·拍。

1×1 共执行 **873,725,952 MAC，占总 MAC 的 93.42%**。其 MAC 脉冲仅占本类 active 的 39.25%，本类仲裁等待仅占 active 的 0.128%。自研核在 `MAC_READ` 与 `MAC_ACC` 间交替，一个实例每两拍执行一次 MAC；两套实例合计在本批次达到 0.7677 MAC/拍。从 active 中扣除每个 MAC 的两拍后，剩余 478,818,876 实例·拍包含输入/权重装载、写回、状态切换及仲裁等成本，不能全部归为 bank 冲突。优先方向是将1×1 MAC读数与累加做流水、增加适量并行MAC并提升装载效率，再比较增加1×1实例的资源收益。本次没有重综合或重新扫描全网实例数量，不宣称改为四套1×1就能得到某个确定加速倍数。

| 算子池 | 数量 | 平均忙碌率 | work 实例·拍 | 仲裁等待 实例·拍 | 等同类资源 帧·拍 |
|---|---:|---:|---:|---:|---:|
| 3×3 / DW3 | 4 | 4.51% | 61,415,424 | 2,093,347 | 0 |
| 1×1 | 2 | 97.81% | 873,725,952 | 2,842,460 | 2,016,986,427 |
| DW7 | 1 | 0.01% | 12,544 | 192 | 0 |
| Post | 1 | 6.08% | 13,625,344 | 710,420 | 3,495,305 |
| Add | 1 | 0.91% | 1,455,104 | 92,380 | 0 |
| Pad | 1 | 0.87% | 2,058,800 | 184,848 | 0 |

平均忙碌率 = 同类实例 active 总和 /（实例数 × 批次周期）；不同实例的周期不能直接相加为批次耗时。卷积 work 为 MAC 脉冲，DW7 每次 work 含 8 路 MAC；Post/Add/Pad 的 work 为成功接受写回。work、wait 都不是与 active 互斥的分项。

进一步依据已核对的状态机与真实 MAC/读写计数，可将两套1×1累计 active 分解如下。每次字节读、每次32位写分别经历请求与正常响应两拍；反压额外计数。这里的分母是 **2,226,270,780 实例·拍**，不是全局批次时间：

| 1×1内部阶段 | 累计实例·拍 | 占1×1 active |
|---|---:|---:|
| MAC_READ + MAC_ACC | 1,747,451,904 | 78.4923% |
| 字节读请求/正常响应 | 459,123,712 | 20.6230% |
| 32位写请求/正常响应 | 16,809,984 | 0.7551% |
| 请求仲裁反压 | 2,842,460 | 0.1277% |
| 其余块切换/状态设置 | 42,720 | 0.0019% |

SRAM `valid && !ready` 仲裁等待合计 5,923,647 实例·拍，占全部算子 active 合计的 **0.23%**。这项已观测到的仲裁反压占比较小，不能用它解释主要耗时。等待 SRAM 正常响应、逐字节访问和单在途请求的固定成本不计入此项，因此不能据此声称没有访存瓶颈。

`capacity_wait_by_opcode` 与 `scan_wait_by_opcode` 都是各图累计的等待帧·拍，不是批次周期百分比；后者表示有同类空闲单元时仍未启动，还包括槽释放和调度扫描等，不能称纯调度耗时。

下表按四图合计层跨度排序。跨度包含该层各算子及其中等待，反映本轮执行路径，不能当作纯 MAC 时间：

| 网络层 | 类型 | 输出 H×W×C | 四图合计层跨度 | 最大单图层跨度 |
|---:|---|---|---:|---:|
| 3 | Conv | 56x56x128 | 272,051,528 | 68,543,721 |
| 2 | Conv | 56x56x64 | 135,865,074 | 33,974,897 |
| 22 | Conv | 28x28x256 | 134,738,321 | 33,715,124 |
| 49 | Conv | 14x14x512 | 131,564,915 | 32,899,243 |
| 6 | Conv | 28x28x128 | 67,613,964 | 16,933,929 |
| 10 | Conv | 28x28x128 | 67,589,914 | 16,919,108 |
| 14 | Conv | 28x28x128 | 67,587,981 | 16,917,531 |
| 18 | Conv | 28x28x128 | 67,579,727 | 16,912,448 |

本报告据已测资源忙碌与等待定位下一步优化对象；没有用短流程数据代替全网测量，也没有假设增加一个算子就必然获得同等比例收益。

## 数值与输出含义

每个场景完成 524 个任务、935,241,728 次标量 MAC；检查 **77,349,168 个输出字节**、524 次分配和 524 次释放。检查方法为每次真实 RTL 写请求逐字节比较整数 golden，同时核对后续真实 SRAM 读响应；最终向量、只读区和槽尾保护区经 SRAM 端口实际读取。不是所有中间张量都另做一次完整读回。

最终每图输出 **128 个 UINT8 分量**，不是 IEEE 浮点。反量化为 `(code - 128) × 0.020234474268826571`；CSV 保留原始量化字节，并另给出反量化近似值。全图共用第一张图得到的诊断尺度，未做代表性数据集校准，也未测人脸识别精度。 独立浮点诊断中四图反量化输出与 FP32 的 RMSE 为 0.1238～0.1656，余弦相似度 0.9760～0.9897；量化输出与 FP32 **不是逐值相同**。模型末尾 Reshape 仅改变形状，分量次序不变；模型及本入口均未加 L2 归一化。

- [原始 UINT8 向量](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/embeddings_u8.csv>)、[反量化近似向量](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/embeddings_dequantized.csv>)、[格式与尺度](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/embedding_format.json>)。
- 四图最终输出 SHA256：`80351fb04be5c55bc45d6e6fcadaef6680b20d0532d15f7bb5bf5c661416a44f`。
- 原始 `outputs.bin`、metrics、events 与运行签名保存在 [evidence](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/deliverables/self_cnn_full_frames/evidence>)。

初始执行内存只含共享权重/量化参数和 A5；运行中的图像通过实际端口写入，所有中间 golden 都只存在于 checker 文件。preloaded 场景若出现在下表，是实际 CPU A 口预装图片后运行；不等同于处理器执行固件。

| 完整运行场景 | 状态 | 批次周期 | 仿真计算耗时（主机） |
|---|---|---:|---:|
| overlap | PASS | 1,138,093,351 | 2620.830 s |

## 存储与实现边界

**本入口使用 16 MiB 的仿真 SRAM 参数，执行初值为 12,608,512 字节（12.024 MiB）。这不代表 Zynq-7020 能在片内容纳此存储。** 四个复用工作区每个 2,810,112 字节，共享只读/输入区域 1,368,064 字节。真实板级实现仍需分块/外存方案及资源、布局布线、时序验证。

本轮证明完整图的量化整数算术、四图自主调度及跨图重叠，不证明识别精度、CPU/UART 集成或板级性能。上方100 MHz仅为条件换算。原 Post / DW7 存储综合问题不因 RTL 仿真 PASS 自动消失；本轮没有新的完整顶层LUT/FF/BRAM/DSP报告，不能用单卷积资源乘实例数代替完整资源占用。

## 复现与来源

- 运行目录：`D:\zhang\fpga-cnn\cpu_control (2)\cpu_control\build\runs\20261023_180539_292440_self_full`。
- 数据目录：`D:\zhang\fpga-cnn\cpu_control (2)\cpu_control\build\self_full_data`；模型 SHA256：`d8da67c4665b97106cb2d98ac569bb02c8a9c6c836c1a8b7b7e5ea5d02591a4f`。
- 生成器：`scripts/gen_self_full.py`，运行器：`scripts/run_self_full.py`，本报告：`scripts/prepare_self_full.py`。
- 报告命令：`python scripts/prepare_self_full.py "D:\zhang\fpga-cnn\cpu_control (2)\cpu_control\build\runs\20261023_180539_292440_self_full" --scenario overlap`。
- 全网运行必须先通过同一可执行文件的小图 gate；报告只接受全网 PASS，SMALL 自测输出被限制在 build 目录。
