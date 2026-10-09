# 任务队列

当前队列由流式描述符读取器和可乱序派发的等待窗口组成。
CPU仍只写 INPUT_ADDR(+0x08)=任务表地址、FEATURE_SIZE(+0x18)=条数，再写 CONTROL=0x3D。
每条描述符32字节，版本号1，little-endian；MMIO及RAM引脚未增加。

完整字段、算子编号、参数记录、依赖规则和错误语义见 [heterogeneous_ops.md](heterogeneous_ops.md)。

```powershell
python scripts/pack_queue.py build/my_model
python scripts/run_tests.py operator_queue --queue-dir build/my_model
```

operator_queue逐项检查导出配置的golden结果，默认仿真RAM为512KiB、最多64条检查项；硬件队列条数不受这个测试台数组大小限制。
TASK_PREFETCH_DEPTH是等待窗口容量，默认4；并发资源为两个阵列上下文和六个独立标量单元。
任务可乱序派发、乱序完成。queue_completed是计数，不能当作连续退休编号使用。
