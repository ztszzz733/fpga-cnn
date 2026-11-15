# RV32I 五级流水线 CPU Datapath

本目录包含完整 `cpu_datapath` 主体，以及C1共享编码、PC、ALU、立即数、寄存器堆、流水寄存器、LSU、地址译码和同步IMEM适配器。完整测试使用独立的 test-only Control、同步IMEM/Data SRAM和CNN MMIO模型。

`rtl/common/cpu_control_pkg.sv` 当前是以 M 方 C1 v1.0 生产定义为基准的兼容版候选：完整保留 M 方正式符号和 `decode_t`，并提供既有 Datapath 名称的等值别名以及 RV32I LOAD/STORE 符号。真实集成时只能编译这一份物理 package，不能同时编译 M 方目录中的同名文件。该候选尚未获得 M 方对新文件哈希的正式冻结确认；当前检查只证明源码编译兼容，不代表真实 Control 或 CNN 联调通过。

Data SRAM采用“所有load/store均在EX→M边界提交，load在M周期返回并于M→W沿采样”。CNN寄存器访问在M级提交并要求零等待。接口和覆盖详见 `docs/cpu_datapath_interface.md`。当前仍未连接M方真实Control或Z方真实CNN，测试通过不代表三方联调完成。

运行基础测试：

```bash
chmod +x scripts/run_base_tests.sh
./scripts/run_base_tests.sh
```

要求：Verilator 5.x、支持 SystemVerilog-2017 的 C++ 编译环境。

本机已使用 Verilator 5.050 实际运行基础测试，结果输出 `PASS: base datapath modules`。可按上面的命令复现。

共享 package 单元测试与 M 方 Control 编译兼容检查：

```bash
./scripts/run_pkg_tests.sh
./scripts/check_control_pkg_compat.sh
```

两项检查分别使用 `build/pkg` 和 `build/control_pkg_compat`，且只编译 Datapath 工程内的兼容版 package。实际执行结果与哈希见 `docs/cpu_control_pkg_compatibility.md`。

运行 LSU 与地址译码单元测试：

```bash
./scripts/run_lsu_tests.sh
```

测试使用独立的 `build/lsu` 目录；覆盖详情与接口说明见 `docs/lsu_address_decoder.md`。

运行固定一周期同步 IMEM 取指适配器测试：

```bash
./scripts/run_fetch_tests.sh
```

测试使用独立的 `build/fetch` 目录，覆盖连续取指、暂停缓存、flush/reset、PC 回绕和压力序列；逐沿契约见 `docs/fetch_adapter.md`。

运行固定一周期同步 Data SRAM 时序测试：

```bash
./scripts/run_dmem_timing_tests.sh
```

测试使用 `build/dmem_timing` 和工程内 `build/tmp`，验证同步读 NBA、现有 MEM/WB 配对、连续 load/store、LSU lane/对齐/边界和副作用门控。最终选择方案 B 的统一 EX 提交变体，不修改 C1。

运行完整Datapath机器码集成测试：

```bash
./scripts/run_datapath_tests.sh
```

当前完整回归命令：

```bash
./scripts/run_pkg_tests.sh
./scripts/run_base_tests.sh
./scripts/run_lsu_tests.sh
./scripts/run_fetch_tests.sh
./scripts/run_dmem_timing_tests.sh
./scripts/run_datapath_tests.sh
./scripts/check_control_pkg_compat.sh
```

## 最终独立交付

Datapath主体已完成独立验收。总回归命令为：

```bash
./scripts/run_all_datapath_tests.sh
```

最终验收报告：`docs/datapath_final_acceptance.md`  
SHA-256清单：`docs/datapath_release_sha256.txt`  
交付包：`deliverables/face_recognition_soc_datapath_complete.zip`

当前仍未完成真实M方Control、Z方CNN、双口共享SRAM/B口适配或SoC顶层集成；独立验收通过不得解释为三方真实联调完成。
