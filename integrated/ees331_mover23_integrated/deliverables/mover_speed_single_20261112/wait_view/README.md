# 怎样看CNN是否因访存而等待

先双击open_wait_detail.cmd打开原有128拍局部波形，熟悉状态/ACTIVE/WORK的对应；open_wait_full.cmd看整图。局部波形未覆盖全部等待事件。两个会话都只读取原始FST，新增显示43根唯一信号；没有重跑仿真或修改原始波形。full/detail会话静态核对信号存在；actual_read_wait小窗口已通过隐藏GTKWave实际加载验证：43根信号、43根唯一，自动定位和退出。

1. 先找ACTIVE=1的算子。ACTIVE=0/IDLE_NO_TASK表示没有分配任务，不能归因为等待数据。
2. K3的INPUT_REQ/WEIGHT_REQ是申请读取阶段，INPUT_WAIT/WEIGHT_WAIT是等待返回阶段；OUTPUT_REQ/OUTPUT_WAIT是结果写入阶段。K1的INPUT_LOAD/WEIGHT_LOAD包含请求、数据返回、缓存装载整个阶段，不能把整个阶段都说成纯等待。MAC_RUN是计算阶段，也可能有内部气泡或预取。
3. 卷积WORK=1表示本拍有实际乘加推进；ACTIVE=1且WORK=0只是非MAC周期，不自动表示访存阻塞。Post/Add/Pad的WORK表示输出写请求被接受，不是它们全部算术活动的标志，不能用它们WORK=0断言没做计算。
4. 同时看MEMORY_STATE_TEXT：PAGE_FILL_REQ/PAGE_FILL_WAIT是调入页，WRITEBACK_REQ/WRITEBACK_WAIT是写回页，LOCAL_ACCESS/LOCAL_REPLY是普通本地RAM访问/返回。MOVER_STATE_TEXT进一步区分DDR读、本地RAM传输、DDR写。PAGE_FILL_WAIT涵盖整个调页过程，不等于每拍都在等待DDR；WRITEBACK_WAIT同理。
5. 若有任务的卷积停在INPUT_WAIT/WEIGHT_WAIT，WORK=0，同时存储处于PAGE_FILL_WAIT/WRITEBACK_WAIT，是明显的访存等待线索。本图为单图顺序任务，记录multiple_active_operator_cycles=0；仍不能把所有搬运忙周期直接等同于卷积空等，结果flush也可能发生在算子结束之后。

## 现有记录的边界

本FST没有逐算子的请求valid/ready/response、读写方向和request_owner；不能精确还原每拍“哪个请求因仲裁/缺页而被阻塞”。DDR_RETURNING_DATA和DDR_SENDING_DATA分别来自RVALID/WVALID，缺少READY时不能直接当作实际握手成交拍。

要精确测纯读等待，下一轮应记录：每算子valid/ready/write/response/WORK，以及读请求在途标志、存储request_owner、内存FSM；按时钟沿判断请求未接收、已接收未返回，并检查同时有没有MAC推进。读取等候与纯计算停顿应分别统计。不要把所有WORK=0都计成浪费。

## 已有阶段统计（100MHz仿真参考）

PAGE_FILL_WAIT=150.16917ms；WRITEBACK_WAIT=75.76440ms。两者合计225.93357ms；加WB_REQ/FILL_REQ阶段后为226.37084ms，占1117.35457ms窗口约20.26%。这是存储阶段占用，不是严格CNN纯等待；与算子加载阶段可能重叠，不能重复相加。卷积MAC活跃共339.04896ms，其余时间还包含后处理、补边、普通RAM读写和配置，不能全部归为浪费。

## 已截出的真实读取等待窗口

先打开open_actual_read_wait.cmd，在工具栏选择Zoom Fit以适应整个小窗口。K3_0在9.957585ms处为ACTIVE=1、WORK=0、读取等待状态，同时存储为PAGE_FILL_WAIT；到9.963245ms退出这一次读取等待。该观测区间长5660.0ns，是从首次满足条件处到退出状态的时间，不是从请求提交开始测得的完整延迟。原始绝对时间未移动；数据全部来自已有full_states.fst，未重跑。

原full_operator_detail的128拍窗口约为160.50088～160.50216ms，主要在K1 SETUP，不是缺数据等待示例。
