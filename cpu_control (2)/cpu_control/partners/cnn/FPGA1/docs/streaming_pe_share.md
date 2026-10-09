# 流式读取与共享PE

当前调度规则见 [heterogeneous_ops.md](heterogeneous_ops.md)。

阵列任务继续按连续PE行分配，两个上下文共用64个PE。每个任务在其行分区内按输出通道、空间位置和归约维度分块。
新增标量单元不占用PE，可以和两个阵列上下文并发运行。

一条描述符完整读回即可派发，不等待整个队列。
与前版不同，现在允许窗口中的独立任务越过资源或数据未就绪的任务；必须先检查与更早待执行任务及所有在途任务的数据冲突。
默认等待窗口4条，RAM仲裁9路，最多8条任务在途。

原Conv/DW并发示例：python scripts/concurrent_wave.py --open。
推荐的多算子示例：python scripts/operator_wave.py --open。
