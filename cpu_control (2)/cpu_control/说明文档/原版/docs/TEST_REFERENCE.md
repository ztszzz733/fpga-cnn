# 换电脑与高级用法

在当前电脑上运行测试，只需按 [第一次运行教程](README_TEST.md) 操作。换电脑安装工具、修改测试或排查具体信号时，再查本页。

本页保留完整命令和参数供查询；初次运行无需逐项配置。文中的 Control 是控制模块，Datapath 是数据通路，stub 是简化测试模型，TB 是自动测试代码。

## 1. 换电脑：准备工具

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

## 2. 需要时再调整参数

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

## 3. 添加一条测试

译码数据在 `tb/vectors/decode_cases.csv`，文档副本在 `docs/decode_table.csv`。每行含 name、opcode/funct 条件、mask、instruction、illegal，以及所有单独控制字段和 expected 打包值。先从 ISA 与 C1 表独立确定预期，再加入新行；不要读取 DUT 输出填期望。

例如手工指令 `fff08293` 是 ADDI x5,x1,-1。它的控制与 ADDI 行相同：ALU=ADD、B=IMM、regwrite=1、imm=I、use1=1、use2=0。可以复制 ADDI 行，仅改名称和 instruction；若固定此手工机器码，把 mask 改为 ffffffff。非固定随机模板只能随机化不影响合法性和控制字的位。

expected 的打包顺序见 module_map.md。如果改了控制字段，也必须同步修改打包值；主 TB 会逐字段打印错误信号名。Golden 表完全独立于 DUT，不会随 RTL 自动变成正确答案。修改后同步文档表，运行 `--test decode --verbose`。

新增冒险测试可在主 TB 的 run_forward 或 run_load_use 中增加分支，设置阶段编号、valid、使能，并写明确的 ck 预期。例如 M/W 同名命中应期待 MEM；M 是 Load 时期待原值并标出不可消费，不能期待旧 WB。刺激在下降沿设置，稳定 1/4 周期后检查。

新增连续序列放在 run_pipeline，先 init_link 复位，再写 test-only imem/dmem。step_link 在下降沿检查已完成的上升沿结果，避免调度竞争。生产模块之间没有层级引用；TB 对 stub 的初始化和故障注入属于验证操作。

## 4. 调整波形与自行导出

把路径替换成终端打印的实际 RUN_DIR，不要把尖括号占位符原样输入。

```powershell
python scripts/plot_waveforms.py --vcd build/runs/本次目录/waves/cpu_control.vcd --signals scripts/wave_signals.json --out-dir build/runs/本次目录/figures --group hazard --test-name all --seed 1
```

需要精确窗口时，先打开 case_windows.json，把 forwarding 的 start_ns/end_ns 传给 `--start-ns`、`--end-ns`，例如任务书的 100..300 仅是 CLI 形式示例，不能假定每次事件发生在同一绝对时间。

`wave_signals.json` 集中管理 clock、decode、ex、hazard、gating、pipeline 分组，entry 中 path 为完整路径、label 是显示名、enum 是编码标签、radix 可选 dec、optional=true 表示允许缺失并警告。严格 JSON 中不要加注释。缺少必选路径直接报错，不按 basename 模糊查找。

安装 GTKWave 后也可执行 `gtkwave 本次路径/waves/cpu_control.vcd`；先添加 clk、pc_en、if_id_en、id_ex_flush、fwd_a 及 link 下 valid/MEM/WB 信号，再缩放到 case_windows 指定范围。无需 GTKWave 时直接看 PNG/SVG。

绘图解析测试：`python -m pytest -q tests/test_plot_waveforms.py`，覆盖多种 timescale、别名、初始 dumpvars、X/Z、同时间事件、常量、窗口继承及缺失信号。合成 fixture 只验证解析器；交付的四张示例图来自真实 RTL 仿真。

## 5. 深入排查问题

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

## 6. 接入真实数据通路

D1 已原则接受 C1；先完成公共地址和真实存储时序冻结，并核对回传 RTL 与 C1 的差异，再逐端口替换样例中的 test-only stub。双方共用唯一 cpu_control_pkg.sv。确认 valid/编号/uses/branch/jump 同条指令，D 控制确实流水，显式 WB→ID 旁路可见，MEM 数据采样符合契约；复位优先级与单次提交都需验证。同步 IMEM 还需丢弃 redirect 前的错误路径返回值。

然后使用真实 CPU 程序检查寄存器、Store、CNN MMIO 和完成条件；tohost 的地址由系统配置另行确定。本 Control 组合测试没有 tohost。逐项要求见 datapath_connection_checklist.md，不能只用结构编译成功宣称真实直连成功。
