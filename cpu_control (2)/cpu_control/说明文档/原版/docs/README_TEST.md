# CPU_CONTROL 从零运行测试

本工程交付 CPU_CONTROL 的组合 RTL，以及为了验证它而写的简化 Datapath 模型。真实 CPU_DATAPATH 和 CNN 运算模块没有提供，因此本工程通过不表示整个 SoC 或人脸识别已经完成。首次阅读建议按本页顺序操作。

## 1. 文件与三个验证层次

`rtl/common/cpu_control_pkg.sv` 定义 C1 编码；`rtl/cpu_control/` 六个文件是交付给 Datapath 负责人的生产 Control RTL。`tb/unit/tb_cpu_control.sv` 是主 testbench（TB），负责产生输入和自动比较结果。DUT 是被测 `cpu_control`，不能把 TB 的延迟、初始化、文件操作移入生产 RTL。

1. 组合验证：直接给指令、流水元数据和比较标志，核对全部控制输出。
2. stub 时序验证：`tb/models/control_datapath_stub.sv` 持有 PC、寄存器及 D/E/M/W 状态；`tb/integration/cpu_control_link_example.sv` 显式连接 Control 与此模型。测试暂停、前进、冲刷和受限数据结果。
3. 真实 Datapath 联调：目前未运行。接到真实代码以后再按连接清单实施。

stub 有 256×32 位 IMEM 和数据数组，仅承诺测试涉及的对齐 LW/SW 和基础运算/跳转序列。它没有真实 DMA、CNN 寄存器组、取指等待、异常或总线握手。数组初始为 0，IMEM 的 0 用作无效填充，而非已测试的非法指令执行策略。真实非法译码在组合测试中验证。

D1 对齐后，`pipeline_D1_safe_NOP` 还用非零非法编码及 FENCE/ECALL/EBREAK 连续执行，检查无架构副作用。stub 和接线样例支持 SystemVerilog 参数 `RESET_PC`，默认 `32'h0000_0000`；它不属于 Control 端口或运行期 plusarg。`stub_D1_RESET_PC_parameter` 使用另一个参数为 `32'h40` 的实例，检查首次取指、AUIPC、后续依赖及同步运行中复位。参数须在 stub 的 1 KiB IMEM 内且 4 字节对齐，最终系统地址待三方冻结。

Control 单元测试不需要 RISC-V 交叉编译器、tohost、完整程序镜像或 UVM。C 示例的宿主语法检查也不等于 RISC-V 交叉编译或 CNN 功能测试。

## 2. 前置工具

需要 Python 3.10+（本机验证 3.11.9）。优先 Icarus Verilog + vvp；若已装 Vivado，也可选择 XSim。本机实际执行的是 Vivado Simulator 2026.1，Icarus/Verilator 未安装，未声称已在它们上执行。

Windows PowerShell：

```powershell
cd D:\cpu_control
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts\requirements.txt
.\.venv\Scripts\python.exe scripts\run_tests.py --check-tools
```

不必激活虚拟环境，直接调用其中的 python 可以避开本机 PowerShell 禁止脚本的策略。本机现有 Python 已有 matplotlib/pytest，可以直接使用 `python`。联网安装依赖时复用 `network/proxy.psd1` 中代理，不需要重新扫描端口。

Linux shell：

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements.txt
iverilog -V
vvp -V
.venv/bin/python scripts/run_tests.py --check-tools
```

缺模拟器时手动安装：[Icarus 官方项目](https://github.com/steveicarus/iverilog)。Linux 可按发行版包管理器安装 iverilog；Windows 可使用团队认可的发行包或 MSYS2，并把包含 iverilog.exe/vvp.exe 的目录加入当前 PATH。脚本也识别项目 `.tools/ucrt64/bin`，但本次没有下载工具。

已有 Vivado 时设置 `XILINX_VIVADO` 指向 Vivado 安装目录，例如本机 `D:\vivado\2026.1\Vivado`。脚本在本机布局中自动发现它，补充运行时 DLL、Tcl 和 Java 路径，仅影响子进程；没有修改系统环境。其他安装布局可以先使用厂商提供的环境终端。

```powershell
$env:XILINX_VIVADO='D:\vivado\2026.1\Vivado'
python scripts/run_tests.py --check-tools
python scripts/run_tests.py --simulator xsim --test all --waves --plot
```

`--check-tools` 输出实际路径及版本。发现路径不等于工具一定能启动，实际编译、展开、仿真通过后才算验证完成。Verilator 可选，`--lint` 没找到时在 result.json 记录 NOT_RUN，不冒充通过。

## 3. 第一条测试命令

```powershell
python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot
```

这条命令已在当前项目真实执行。它包含 37 条必需指令、项目 NOP/非法码、定向前递/冒险/分支检查、1,000 条随机译码，以及最多 128 个独立约束随机前递状态。随机译码数量与随机冒险数量在 JSON 中分开统计。

按场景运行：

```powershell
python scripts/run_tests.py --test decode --seed 2
python scripts/run_tests.py --test load_use --waves --plot
python scripts/run_tests.py --test branch --waves --plot
python scripts/run_tests.py --test all --seed 2026 --random-cases 5000 --waves
```

`load_use`、`branch`、`jump` 入口还会运行共同的 stub 时序序列，以验证流水反馈与副作用；不是只测一个组合条件。`forward` 只运行前递定向测试，`pipeline` 只运行 stub 序列。没有运行译码的子集不会把默认 1,000 条随机译码计为已执行，result.json 的 random_scheduled 为 0。

PowerShell/Bash 薄封装调用同一个 Python：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_tests.ps1 --test decode --seed 2
```

```bash
bash scripts/run_tests.sh --test all --waves --plot
```

PowerShell 的 Bypass 只作用于此次进程，不改系统策略。Python 入口不依赖工作目录，例如在其他目录用 `python D:\cpu_control\scripts\run_tests.py ...` 也能正确定位工程。Linux 入口已提供，但本机没有执行 Linux 版模拟器；Windows 中文且含空格的结果目录已经实测。

## 4. 参数怎么改

集中配置文件为 `tb/config/tb_config.svh`，可编辑部分有 USER EDIT BEGIN/END。脚本读取其中默认值，再由命令行覆盖，最后作为 plusargs 传给 TB。脚本每次重新编译，修改配置不会被旧快照掩盖。

| 命令行参数 | 配置/plusarg | 默认 | 范围及作用 |
|---|---|---|---|
| --test | TEST_NAME | all | decode/forward/load_use/branch/jump/reset/pipeline/all |
| --seed | SEED | 1 | 0..2147483647，固定种子可复现 |
| --random-cases | RANDOM_CASES | 1000 | >=0；0 跳过随机，定向仍运行 |
| --clk-period-ns | CLK_PERIOD_NS | 10 | >=2 的偶数 ns；仿真精度 1 ps |
| --reset-cycles | RESET_CYCLES | 3 | >=2 完整周期 |
| --max-cycles | MAX_CYCLES | 10000 | >0，全局仿真周期保护 |
| --waves / --no-waves | DUMP_WAVES | 1 | 是否生成 VCD；--plot 自动启用 |
| --verbose | VERBOSE | 0 | 每个检查输出日志 |
| --stop-on-first-error | STOP_ON_FIRST_ERROR | 1 | 0 继续收集错误，但最终仍失败 |
| --timeout | 脚本进程超时 | 120 秒 | 每个外部编译/仿真进程的墙钟上限 |
| --out-root | 结果根目录 | build/runs | 可含中文与空格；每次生成新的子目录 |
| --simulator | 脚本选择 | auto | auto/icarus/xsim，auto 优先 Icarus |
| --plot-start-ns / --plot-end-ns | 绘图窗口 | 实际场景窗口 | 不可为空、倒序、超出 VCD |
| --plot-signals-file | 信号配置 | scripts/wave_signals.json | 完整层级路径与枚举 |
| --lint | 可选检查 | 不运行 | Verilator 不存在会明确记录 NOT_RUN |

VCD_PATH 和 VECTOR_PATH 由脚本设置为独立运行目录内的相对路径，避免外部工具把中文空格路径拆开。直接运行已编译 TB 可以用同名 plusargs 覆盖，例如 Icarus `vvp sim.vvp +TEST_NAME=decode +SEED=2 ...`；但要自行准备与 SEED/RANDOM_CASES 一致的 vectors.txt。推荐始终使用 Python 入口。

测试代码字段位宽和 C1 枚举属于接口契约，不是普通用户参数。没有“任意 MEM 延迟”选项，因为目前没有 MEM ready/stall；读延迟不符合边沿契约时必须扩展接口。

例：增加随机量时同时保留足够周期，避免人为超时：

```powershell
python scripts/run_tests.py --seed 42 --random-cases 12000 --max-cycles 20000 --no-waves
```

## 5. 添加一条测试

译码数据在 `tb/vectors/decode_cases.csv`，文档副本在 `docs/decode_table.csv`。每行含 name、opcode/funct 条件、mask、instruction、illegal，以及所有单独控制字段和 expected 打包值。先从 ISA 与 C1 表独立确定预期，再加入新行；不要读取 DUT 输出填期望。

例如手工指令 `fff08293` 是 ADDI x5,x1,-1。它的控制与 ADDI 行相同：ALU=ADD、B=IMM、regwrite=1、imm=I、use1=1、use2=0。可以复制 ADDI 行，仅改名称和 instruction；若固定此手工机器码，把 mask 改为 ffffffff。非固定随机模板只能随机化不影响合法性和控制字的位。

expected 的打包顺序见 module_map.md。如果改了控制字段，也必须同步修改打包值；主 TB 会逐字段打印错误信号名。Golden 表完全独立于 DUT，不会随 RTL 自动变成正确答案。修改后同步文档表，运行 `--test decode --verbose`。

新增冒险测试可在主 TB 的 run_forward 或 run_load_use 中增加分支，设置阶段编号、valid、使能，并写明确的 ck 预期。例如 M/W 同名命中应期待 MEM；M 是 Load 时期待原值并标出不可消费，不能期待旧 WB。刺激在下降沿设置，稳定 1/4 周期后检查。

新增连续序列放在 run_pipeline，先 init_link 复位，再写 test-only imem/dmem。step_link 在下降沿检查已完成的上升沿结果，避免调度竞争。生产模块之间没有层级引用；TB 对 stub 的初始化和故障注入属于验证操作。

## 6. 怎么判断成功、失败

每次先打印 `RUN_DIR=...`。成功示例（数字仅为格式说明，以本次日志为准）：

```text
SUMMARY cases=... checks=... random=1000 seed=1 failures=0
PASS CPU_CONTROL all
PASS D:\cpu_control\build\runs\某次运行\result.json
```

失败会给 case_id、scene、cycle、时间、signal、actual 和 expected。例如 `scene=pipeline_load_use signal=consumer_WB_forward` 应先看这一场景的 fwd_a、valid_w、rd_w、WB_data。译码失败的 `decode_vector_N` 可在同次运行的 vector_index.csv 找到指令和名称。

超时示例为 `TIMEOUT cycle=... max_cycles=... case_id=...`。退出码 0 表示请求的流程成功；1 表示编译、仿真、超时或绘图失败；2 表示参数或工具条件不满足。即使 XSim 把 `$fatal` 当成正常关闭，脚本也要求出现有效汇总和 PASS 标记，不会把它算成功。

以下是**预期失败**的检查命令，不是正常验收：

```powershell
python scripts/run_tests.py --test reset --negative-case mul_busy --no-waves
python scripts/run_tests.py --test decode --max-cycles 2 --no-waves
```

第一条验证非零 mul_busy 被拒绝，第二条验证全局超时会失败。`--stop-on-first-error 0` 会收集更多检查错误，但最后仍非零退出。编译失败一般没有可绘 VCD；仿真失败若已产生 VCD，--plot 会尽量生成标注 FAILED 的调试图片。

## 7. 结果在哪里

`build/runs/日期_时间_微秒_测试名_seed种子/` 下，每次独立保存：

- compile.log：编译及展开命令与完整输出。
- simulation.log：实际仿真命令、配置、失败或 PASS 汇总。
- result.json：总状态、版本、种子、命令、计数、未运行项目、错误。
- tb_summary.json：完成仿真的功能计数；提前 fatal 时可能没有。
- vectors.txt、vector_index.csv：本次固定/随机机器码及预期索引。
- case_windows.csv / case_windows.json：TB 标记的实际场景时间窗口。
- waves/cpu_control.vcd：本次 RTL 仿真数据。
- figures/decode、forwarding、load_use、branch_flush 的 PNG/SVG：有对应场景且 --plot 时生成。

文件不会复用旧运行的 VCD 或图片。缺少所需信号、图片生成失败或空窗口都让 --plot 流程失败。请保留整个运行目录，避免图片失去源 VCD。正式交付图另存 docs/figures，来源记录在 verification_report.md。

## 8. 读懂两张关键波形

Load-use 图的局部时间起点见 case_windows.json。第一条 LW 进入 E 时，ADD 停在 D：pc_en/if_id_en 拉低，id_ex_flush 拉高。下一个上升沿之后，LW 在 M、E 是气泡、ADD 仍在 D。再下一个上升沿，ADD 到 E，LW 到 W；fwd_a=WB，WB_data=0000002A（42）。最终 ADD 的结果为 00000031（49），reg commits 变为 2。MEM 周期不能被冻结。

Branch flush 图中，BEQ 进入 E 后 pc_sel=TARGET、两路 flush 同时为 1；下一沿 D/E valid 都清零，错误路径的 x7 写入和 Store 未提交。目标路径 x8=1 正常提交，stores 始终为 0。branch 自身继续经过 M/W，但没有 regwrite。

单比特阶梯的高低代表 1/0；总线显示稳定区间内的十六进制或枚举。黄色斜线是 X，紫色是 Z，不会转为 0。边界极短区间可能不标数值以防文字重叠；需要检查时缩小窗口，源 VCD 保留所有事件。

## 9. 自行导出与 GTKWave

把路径替换成终端打印的实际 RUN_DIR，不要把尖括号占位符原样输入。

```powershell
python scripts/plot_waveforms.py --vcd build/runs/本次目录/waves/cpu_control.vcd --signals scripts/wave_signals.json --out-dir build/runs/本次目录/figures --group hazard --test-name all --seed 1
```

需要精确窗口时，先打开 case_windows.json，把 forwarding 的 start_ns/end_ns 传给 `--start-ns`、`--end-ns`，例如任务书的 100..300 仅是 CLI 形式示例，不能假定每次事件发生在同一绝对时间。

`wave_signals.json` 集中管理 clock、decode、ex、hazard、gating、pipeline 分组，entry 中 path 为完整路径、label 是显示名、enum 是编码标签、radix 可选 dec、optional=true 表示允许缺失并警告。严格 JSON 中不要加注释。缺少必选路径直接报错，不按 basename 模糊查找。

安装 GTKWave 后也可执行 `gtkwave 本次路径/waves/cpu_control.vcd`；先添加 clk、pc_en、if_id_en、id_ex_flush、fwd_a 及 link 下 valid/MEM/WB 信号，再缩放到 case_windows 指定范围。无需 GTKWave 时直接看 PNG/SVG。

绘图解析测试：`python -m pytest -q tests/test_plot_waveforms.py`，覆盖多种 timescale、别名、初始 dumpvars、X/Z、同时间事件、常量、窗口继承及缺失信号。合成 fixture 只验证解析器；交付的四张示例图来自真实 RTL 仿真。

## 10. 常见问题

| 现象 | 处理方式 |
|---|---|
| 找不到 iverilog/vvp | --check-tools 查看路径；手动安装或选择已装 XSim |
| 找不到 package/类型 | 按 filelist 顺序编译，package 必须第一，TB 最后，启用 SV |
| 端口不存在/位宽不同 | 对照 C1 逐端口表；不能给缺失反馈绑常量掩盖差异 |
| latch/多驱动警告 | 检查完整组合默认值和唯一驱动；先修复，再验收；XSim 无警告不替代专门 lint |
| X/Z 输出 | 看 valid、复位、未初始化反馈；严格限定支持域，不用 casex 掩盖 |
| 一直暂停/超时 | 检查旧 E Load 是否前進到 M、E 气泡是否清 memread；检查 max-cycles 是否过小 |
| Windows Tcl/DLL/Java 路径错误 | 指定 XILINX_VIVADO；使用厂商环境终端；查看 simulation.log 原始报错 |
| 找不到波形信号 | 用 VCD 的完整层级路径；真实 Datapath 更换后同步 JSON |
| 图片空白或总线数值挤压 | 检查时间窗口与场景实际发生时刻，缩短范围，至少 150 dpi |
| 中文字体/路径 | 绘图会选已有微软雅黑/黑体/Noto 字体；信号标签默认英文；外部程序使用参数列表 |
| 只看到旧图片 | 使用本次 RUN_DIR，不要把上次 figures 当成本次产物 |

## 11. 接入真实 Datapath

D1 已原则接受 C1；先完成公共地址和真实存储时序冻结，并核对回传 RTL 与 C1 的差异，再逐端口替换样例中的 test-only stub。双方共用唯一 cpu_control_pkg.sv。确认 valid/编号/uses/branch/jump 同条指令，D 控制确实流水，显式 WB→ID 旁路可见，MEM 数据采样符合契约；复位优先级与单次提交都需验证。同步 IMEM 还需丢弃 redirect 前的错误路径返回值。

然后使用真实 CPU 程序检查寄存器、Store、CNN MMIO 和完成条件；tohost 的地址由系统配置另行确定。本 Control 组合测试没有 tohost。逐项要求见 datapath_connection_checklist.md，不能只用结构编译成功宣称真实直连成功。
