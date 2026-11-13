# 独立显示卷积计算阶段

优先双击open_mac_example.cmd：约10KiB的小窗口，已通过隐藏GTKWave实际加载，40根信号全部唯一。窗口显示K3_0第一次MAC计算前后。open_mac_activity.cmd读取全程计算视图，已设置相同放大位置，首次加载可能较慢；想看全程时使用Zoom Fit。所有时间保留原始坐标；从已有full_states.fst生成，未重跑仿真、未修改RTL或原波形。

每套K3增加：MAC_READ=ACTIVE且原FSM等于8；MAC_ACC=ACTIVE且原FSM等于9；MAC_FIRE直接复制原来的卷积WORK。K1的计算阶段名为MAC_RUN（ACTIVE且原FSM等于6），不是MAC_READ/MAC_ACC。

MAC_READ/MAC_ACC是计算阶段指示，MAC_FIRE才表示本拍有乘加结果推进。MAC_READ阶段也可以有乘加和累加，MAC_ACC主要是最后的流水收尾，不能理解成只有MAC_ACC高时才累加。MAC_FIRE脉冲不是整层/整张图片完成。

原来的STATE_TEXT线上也会显示这两个状态，但在长时间轴上太短容易看不到。这次把它们解码成独立0/1线。全程全部8套卷积均可查看，每个模块的状态、ACTIVE和计算指示放在一起。

首个K3_0 MAC_READ开始：9.963565000ms；MAC_ACC开始：9.963835000ms；离开本次计算阶段：9.963855000ms。

本次检查：小窗口GTKWave实际加载PASS；全程GUI首次加载超过20秒，未宣称完成全程GUI加载验证，保留全程FST及信号列表。全程和小窗口均从原始记录生成，不代表一轮新仿真。
