# 文档入口

- [CPU 内部 RAM 对接与代码交付说明](cpu_internal_ram_integration.md)：源码放置、顶层接线、RAM 共享、CPU 启动方法及联调验收。
- [大模块输入输出与数据／控制分类](module_interfaces.md)：六个功能块、顶层端口、模块间连接和任务执行示例。
- [当前多算子架构与完整队列协议](heterogeneous_ops.md)：先阅读此文；已支持激活、ADD、MaxPool、MatMul和增强量化。

- [当前结构与支持范围](array_only.md)：算子、接口、模块关系。
- [流式任务调度与 PE 共享](streaming_pe_share.md)：边读边算、两个任务分区、依赖等待。
- [任务队列格式](task_queue.md)：MMIO 启动方法和 32 字节描述符。
- [整个加速器时序](accelerator_wave.md)：连续任务从接收到完成。
- [任务读取、配置与缓冲波形](task_setup_wave.md)：queue / buffers / array 三种视图。
- [阵列内部波形](systolic_wave.md)：修改输入、逐拍对照乘加。

当前多算子并发示例运行 `python scripts/operator_wave.py` 后，逐行说明位于 `build/operator_vectors/guide.md`，验证结果位于同目录 `result.json`。

`figures/compute_engine.drawio`、`figures/compute_engine.png` 和 `scripts/draw_compute_engine.py` 是原样保留的手工修改内容。图中单引擎结构不代表当前双任务共享阵列的完整结构；当前架构以以上文档和 RTL 为准。

`integration/` 是历史 CPU 对接记录，保留原文供追溯，不作为本版接口规范。
