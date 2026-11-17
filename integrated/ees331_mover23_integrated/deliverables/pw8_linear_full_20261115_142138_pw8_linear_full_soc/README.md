# 单图SoC：PW8连续分组前后对比

同一张112×112 RGB测试张量、同一129任务网络，两版完整通过。仅PW8源码不同；CPU、K3、后处理、Add、Pad、共享RAM、MOVER和DDR模型完全相同。整图提交到DDR结果可见的周期减少 **1.88%**，其中1×1卷积任务累计周期减少 **4.43%**。

| 口径 | 原4×2分组 | 连续8像素分组 |
|---|---:|---:|
| 图片提交完成→DDR结果可见 | 95,238,605周期 | 93,449,953周期 |
| 按100MHz条件换算 | 952.38605ms | 934.49953ms |
| DDR总读字节 | 28,590,080 | 28,617,728 |
| DDR总写字节 | 16,271,360 | 16,263,168 |
| 电脑实际整图仿真时间 | 496.830s | 423.505s |
| 电脑编译时间 | 81.199s | 59.536s |

电脑总运行1070.234s，含两版编译、小图门槛和两次整图；不含本说明/图片整理。原版不记录全程控制波形，新版记录，因此两版电脑运行时间不能当硬件性能比较。硬件性能比较只看同口径周期数。新版100MHz时序与资源仍按用户要求稍后补测。

## 看哪里

- [交互时间线](index.html)：切换原/新分组，点击任一任务查看尺寸、通道、耗时、读取字节和实际MAC工作拍；可筛选7×7、14×14等1×1层。
- [整体延迟图](overview.png)、[各1×1层收益图](pw8_layers.png)、[全程任务时间线](task_timeline.png)。
- [每个任务的对比表](per_task_comparison.csv)、[测量汇总](summary.json)、[原始运行记录](run_result.json)。
- GTKWave控制波形与打开方式见后续的`wave/`目录和验证记录；原始VCD在`D:/code/FPGA1/integrated/ees331_mover23_integrated/simulation/build/runs/20261115_142138_pw8_linear_full_soc/new/full/control.vcd`。未采集模拟电压波形或板级时序。

## 各类任务累计周期

以下是实际START→COMPLETE区间，包含读取、计算和写回应答；其中等待不能一概算为MAC计算。读取、权重预取、内部写队列可以与MAC重叠，因此各类访存活动不能直接相加成总时间。

| 类别 | 原周期 | 新周期 |
|---|---:|---:|
| K3/DW3 | 17,512,400 | 17,500,084 |
| PW8 | 41,541,991 | 39,701,088 |
| Post | 28,347,621 | 28,415,939 |
| Add | 2,044,979 | 2,035,804 |
| Pad | 5,786,432 | 5,792,105 |

此处为单图，当前调度以任务依赖顺序推进；这次不验证多图同时计算。若其它算子任务耗时略变，是输入请求顺序改变后共享存储/DDR模型时序变化，不能当成这些算子RTL自身又优化了。

## 计算与结果

这是沿用的合成测试图和诊断量化，不是人脸识别准确率测试。运行当前缩减版MobileFaceNet：跳过DW7及其关联Post，保留尾部原参数并在7×7运算，最终输出UINT8/HWC、7×7×128=6272字节；不等价于原模型128维嵌入。

两版129个任务的 **19,365,452字节中间结果** 均逐字节匹配独立整数参考，最终结果完全一致，SHA256：`8971dac0e8b2df60698e060a5e066b416213e8a71553161f66b037e613718485`。同时检查只读模型、写覆盖、缓冲区保护、CPU配置、MOVER双向传输、结果写回fence和批次复位。参考数据没有注入中间执行内存。

PS将输入整图写入DDR后由CPU提交；不含UART串口或边收同一张图边计算。CPU是真实项目RTL，PS GP0和带反压的AXI3 DDR是环境模型；DDR为64MiB仿真地址空间，共享tile RAM为392KiB。

## 波形信号说明

全程按每10ns采样稳定的时钟沿前信号，只记录变化，没有额外记录每拍时钟。GTKWave显示时间为假定100MHz时钟下的仿真时间。

| 信号 | 含义 |
|---|---|
| INPUT_COMMITTED | TB已完成整图写入，随后CPU提交该帧；不等同UART接收完成 |
| CNN_RUNNING | 调度器处于执行批次 |
| COMPLETED_TASKS | 已完成任务计数，最终129；测试最后复位会清零 |
| RESULT_IN_DDR | TB经CPU得到结果描述符，并核对DDR最终结果后置1 |
| OPERATOR_BUSY[11:0] | 各算子忙碌，包含数据准备及等待 |
| ACTUAL_WORK[11:0] | 卷积位表示实际MAC退休；Post/Add/Pad位表示写请求活动，含义不同 |
| REQUEST_VALID[11:0] | 算子向共享存储提出请求；不表示请求已被接受 |
| MEM_PENDING[11:0] | 观察器跟踪已接受、尚未应答的请求；应答当拍清除，是派生观测量 |
| RESPONSE[11:0] | 共享存储返回该算子的读/写应答 |
| MEMORY_STATE / MOVER_STATE | 分页存储控制器与DDR搬运器状态编号 |
| K3_0/1_STATE、PW8_0..5_STATE | 对应实例真实RTL状态编号；不是自创的算子利用率 |
| POST_0/1_STATE、ADD_0_STATE、PAD_0_STATE | 其它算子状态编号 |
| FAULT | CNN或存储错误，成功过程中保持0 |

12位向量的位0/1=K3_0/1，位2..7=PW8_0..5，位8/9=POST_0/1，位10=ADD，位11=PAD。PW8状态依次0IDLE、1SETUP、2CHECK、3TILE_BEGIN、4IREQ、5WREQ、6MAC_RUN、7OREQ、8OWAIT、9DRAIN、10FINISH、11FAIL；K3依次0IDLE、1SETUP、2CHECK、3TILE_BEGIN、4IREQ、5IWAIT、6WREQ、7WWAIT、8MAC_READ、9MAC_ACC、10OREQ、11OWAIT、12FINISH、13FAIL。

MEM_PENDING高不一定表示浪费：PW8可能一边MAC一边预取/写回。`operator_profile.csv`中的pending_no_mac_cycles也只代表“请求未回应且该拍无work”，并非全部可消除的停顿；request_wait_cycles是valid高但ready低。各层任务条同样包含访存等待。

## 复现和源码

入口`simulation/scripts/run_pw8_linear_full_soc.py`。每版使用独立源码快照，生产源码不被切换。原版PW8使用本次优化前已保存的准确源码，其他文件逐项核对相同。原/新版小门槛均通过，新版小门槛的控制记录开/关逐周期结果、事件和统计一致。

运行目录：`D:/code/FPGA1/integrated/ees331_mover23_integrated/simulation/build/runs/20261115_142138_pw8_linear_full_soc`；两版的`source/`及可执行程序留在那里。无自动重复执行、综合或资源测试。

## 打开本次控制波形

- `wave/open_full.cmd`：24根唯一信号，全程输入提交、任务完成、算子状态、MAC活动与共享存储握手。
- `wave/open_pw8_detail.cmd`：第一段7×7 PW8实际MAC附近1024拍，10根唯一信号，便于观察连续运算和等待。
- [波形记录及译码表](wave/wave_result.json)。GTKWave显示的`*_STATE_TEXT`来自实际RTL状态编号，按本次冻结源码的枚举译成ASCII；不是额外硬件状态。原始数值状态仍保留在运行目录`control.vcd`。

`MAC_RUN`表示PW8计算阶段，实际退休拍应结合`ACTUAL_WORK`对应位；计算阶段包含流水填充。`MEM_PENDING`表示已接收请求尚未应答，也可能和MAC重叠。详见上面的信号说明。

## 交付检查

两版完整PASS及源码、数据、输出哈希核对通过；4张PNG已目视检查。GTKWave隐藏窗口实际加载全程24根、局部10根唯一信号，通过保存会话和Tcl验证。局部控制截图由真实VCD绘制：[MAC与访存局部图](control_detail.png)。未使用隐藏窗口的黑色截图。

全程原始VCD约2.27GiB，留在运行目录；交付的全程FST约4.39MiB，局部FST约1KiB，打开交付的FST即可，不必载入大VCD。全程保留数值状态编号，局部将状态译为可读文本。
