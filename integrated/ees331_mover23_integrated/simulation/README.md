# 系统仿真专用目录

这里保存 2026-11-11 的真实 CPU＋23 客户端 CNN 顶层仿真源码、测试输入和记录。`run_pool23_soc.py` 是旧 DDR/cache 路径对照；`run_mover23_soc.py` 使用正式集成目录根部的新顶层，让真实 CNN 经 32 KiB tile RAM、DATA MOVER 访问模拟 DDR。

旧路径范围见 `SYSTEM_SIM_REPORT_20261111.md`；新路径、资源和剩余限制见根部 `docs/storage_mover23_integration_report_20261111.md`。运行 `scripts/prepare_pool23_soc.py` 后执行 `scripts/run_mover23_soc.py four_frame_all_ops`；新路径证据在 `build/mover23_soc/`，故障/取消/恢复证据在 `build/mover23_faults/`。`build/pool23_soc/` 为迁入时的历史运行记录，其中 CMake 缓存含旧目录路径。

运行 `scripts/run_mover23_coverage.py` 可在三次真实顶层仿真中选择不同 K1 实例组，逐字节比较相同图的输出，并确认 23 个 CNN 物理客户端全部至少启动一次。汇总结果在 `build/mover23_soc/coverage23.json`。这是一组客户端接线覆盖测试，不表示 23 个算子同时计算或完整 MobileFaceNet 网络已通过。
