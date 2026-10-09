# FPGA1 CNN 原始交付

接收日期：2026-10-07。

来源 `D:\QQ\FPGA1.zip`，SHA256：
`3C3E6B390C8ADE24E65A8864DB3DC962C92B2411F8391B8CC9CECEAF3B6B016C`。

独立说明 `D:\QQ\cpu_internal_ram_integration.md`，SHA256：
`E822E4CA9E44C461A47FB51DC78878BFB1B8225AD4EB824727B8C91DD065439A`。

提取 `rtl/tb/scripts/docs/examples/README.md/requirements.txt`，不提取交付包内 `.deps/build` 等旧环境和结果。FPGA1 下源码保持原样。

CPU 侧整合见 [小白版修改说明](../../docs/CNN实际代码整合修改说明_小白版.md)。
生产清单共 25 个 SV 文件。XSim 2026.1 不接受 `tensor_operator_engine.sv` 中混合有/无初值的 net 声明，因此系统清单使用 `rtl/compat/tensor_operator_engine.sv`，仅拆开声明和连续赋值。原文件保留，不能把两份同名模块同时编译。

完整独立 CNN 回归仍按 FPGA1 自带工具运行；本工程 `python scripts/run_cnn_integration.py` 验证的是 CPU 与实际 CNN 的连接。

2026-10-08 再次核验同一压缩包：93 个已导入交付文件逐字节一致，现有端口连接可直接复用，本次没有修改 RTL。隔离边界、逐组端口对照和本次仿真结果见 [源码隔离与端口对齐核验](../../docs/fpga1_isolated_port_alignment_20261008.md)。
