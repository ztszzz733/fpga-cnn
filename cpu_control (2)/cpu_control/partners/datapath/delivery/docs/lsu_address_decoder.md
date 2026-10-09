# LSU 数据处理与地址译码

日期：2026-09-15  
状态：第三步纯组合模块实现与单元测试完成；尚未接入完整流水线。

## 1. 模块职责与边界

`address_decoder` 只把一个 32 位字节地址分类为 Data SRAM、CNN MMIO 窗口、CNN 已实现寄存器或全局未映射。它不执行 MMIO 寄存器副作用。

`lsu` 只对一个 32 位存储字进行 RV32I 小端 load 抽取/扩展，并生成 store 对齐数据及四位 byte enable。它不产生总线请求。

两个模块均为纯组合 SystemVerilog：没有 `clk`、`rst_n`、状态机、握手、valid、stall 或时序状态；所有输出均有确定默认值，Verilator 未报告锁存器警告。

## 2. address_decoder 接口

```systemverilog
module address_decoder #(
    parameter logic [31:0] SRAM_BASE     = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE     = 32'h0004_0000,
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000,
    parameter logic [31:0] CNN_MMIO_SIZE = 32'h0000_1000
) (
    input  logic [31:0] addr,
    output logic        sram_hit,
    output logic        mmio_window_hit,
    output logic        mmio_reg_hit,
    output logic        unmapped
);
```

默认 SRAM 字节范围是 `0x0000_0000..0x0003_FFFF`；CNN MMIO 窗口是 `0x4000_0000..0x4000_0FFF`。

范围判断把地址和基址扩展到 33 位后相减，并判断 `offset < {1'b0,SIZE}`。当 `addr < BASE` 时，33 位无符号差值落在大于等于 `2^32` 的区域，不可能小于任意 32 位 SIZE；因此无需计算可能回绕的 `BASE+SIZE`。若合法范围延伸到 32 位地址空间顶部，逻辑自然识别仍可表示的 `[BASE,0xFFFF_FFFF]`，不会错误命中低地址。`SIZE=0` 时范围为空。

## 3. MMIO 寄存器识别

`mmio_reg_hit` 先要求窗口命中，再对 33 位相对偏移做精确 case，仅接受：

| 地址 | 偏移 | 寄存器 |
|---|---:|---|
| `0x4000_0000` | `0x00` | CONTROL |
| `0x4000_0004` | `0x04` | STATUS |
| `0x4000_0008` | `0x08` | INPUT_ADDR |
| `0x4000_000C` | `0x0C` | OUTPUT_ADDR |
| `0x4000_0010` | `0x10` | WEIGHT_ADDR |
| `0x4000_0014` | `0x14` | BIAS_ADDR |
| `0x4000_0018` | `0x18` | FEATURE_SIZE |
| `0x4000_001C` | `0x1C` | CHANNELS |
| `0x4000_0020` | `0x20` | LAYER_PARAM |

窗口内其他地址（含未对齐地址）满足 `mmio_window_hit=1`、`mmio_reg_hit=0`。窗口外两个 MMIO hit 都为 0。`unmapped=!(sram_hit||mmio_window_hit)`，所以窗口内未实现地址不是全局 unmapped。默认范围互斥；模块本身不加入参数重叠仲裁，后续系统参数必须保持 SRAM/MMIO 不重叠。

## 4. LSU 接口

```systemverilog
module lsu (
    input  logic [31:0] addr,
    input  logic [31:0] store_data,
    input  logic [31:0] read_word,
    input  logic [2:0]  load_type,
    input  logic [1:0]  store_type,
    output logic [31:0] load_data,
    output logic        load_aligned,
    output logic        load_type_valid,
    output logic [31:0] store_wdata,
    output logic [3:0]  store_wstrb,
    output logic        store_aligned,
    output logic        store_type_valid
);
```

类型编码只取自工程内唯一的 `rtl/common/cpu_control_pkg.sv`。完整地址端口为以后顶层接线保留；纯组合 lane/alignment 逻辑只需要 `addr[1:0]`，源码对这一明确边界做了局部 `UNUSEDSIGNAL` lint 标注，没有全局关闭 lint。

## 5. Load 规则

对 `read_word[31:0]` 按小端地址选择：

| 类型 | 地址低位 | 选择 | 输出 |
|---|---|---|---|
| LB | `addr[1:0]=0/1/2/3` | `[7:0]/[15:8]/[23:16]/[31:24]` | 8 位符号扩展 |
| LBU | 同上 | 同上 | 8 位零扩展 |
| LH | `00/10` | 低/高半字 | 16 位符号扩展 |
| LHU | `00/10` | 低/高半字 | 16 位零扩展 |
| LW | `00` | 完整字 | 原 32 位数据 |

LB/LBU 始终对齐；LH/LHU 要求 `addr[0]=0`；LW 要求 `addr[1:0]=00`。已知类型即使地址不对齐，`load_type_valid=1`、`load_aligned=0`、`load_data=0`。保留/非法类型输出 `valid=0`、`aligned=0`、数据 0。不产生 X，也不实现 trap。

## 6. Store 规则

使用 `store_data=32'hA1B2_C3D4` 举例：

| 类型/低位 | `store_wstrb` | `store_wdata` |
|---|---:|---:|
| SB/00 | `0001` | `000000D4` |
| SB/01 | `0010` | `0000D400` |
| SB/10 | `0100` | `00D40000` |
| SB/11 | `1000` | `D4000000` |
| SH/00 | `0011` | `0000C3D4` |
| SH/10 | `1100` | `C3D40000` |
| SW/00 | `1111` | `A1B2C3D4` |

SB 任意对齐；SH 要求 `addr[0]=0`；SW 要求低两位为 0。非对齐的已知类型保留 `store_type_valid=1`，但 `store_aligned=0`、`store_wstrb=0`、`store_wdata=0`。非法类型则 valid/aligned/strobe/data 全部为安全确定值 0。

## 7. 为什么不生成请求

本步骤刻意不加入 `dmem_re/we`、`mmio_re/we`、ready、valid 或 stall。LSU 不知道当前流水指令是否有效，address decoder 也不知道是 load 还是 store；在这里生成请求会把组合数据处理与 M 级副作用/同步存储时序错误耦合。

后续 `cpu_datapath` 顶层必须组合 `valid_m`、`memread_m/memwrite_m`、地址命中、类型合法、对齐和 reset 状态：只允许合法有效 SRAM 访问驱动 dmem，只允许对齐 LW/SW 且 `mmio_reg_hit` 的访问驱动 CNN MMIO；未映射或非法读返回 0，写无副作用；任何错误路径不能产生写请求。同一条 store 只能提交一次。

## 8. 与固定一周期同步 SRAM 的边界

LSU 的 `read_word` 是已经由存储器边界提供的完整 32 位字。模块只在组合路径中抽取/扩展，不决定 SRAM 在哪个沿采样地址，也不保存 load 元数据。后续顶层/wrapper 必须满足 M 方 `memory_timing_contract.md`：load 地址在 M 周期稳定，读字在 M→W 沿前满足建立时间，并与同一条指令的 rd/regwrite/wb_sel 配对。若实体 SRAM 更慢或可变延迟，必须升级 C1，不能修改本组合 LSU 假装兼容。

## 9. 测试覆盖与结果

`tb/unit/tb_lsu_address_decoder.sv` 无时钟，每次改变输入后等待 `#1` 再自检，失败累计并最终 `$fatal`。

覆盖包括：默认 SRAM 首尾及越界；MMIO 窗口首尾；九个寄存器逐项；六个窗口内非法/未对齐位置；所有地址的互斥、reg→window 和 unmapped 不变量；`SRAM_BASE=0xFFFF_F000,SIZE=0x1000` 的首/中/末、下界外及低地址防回绕；LB/LBU 四 lane；LH/LHU 两 lane与正负扩展；LW；所有要求的非对齐和非法类型；SB 四 lane、SH 两 lane、SW及 strobe。

干净构建前只删除了以下明确子目录：`build/pkg`、`build/base_modules`、`build/lsu`、`build/control_pkg_compat`，未清理整个 build 或其他目录。

| 顺序 | 实际脚本 | PASS | 退出码 |
|---:|---|---|---:|
| 1 | `./scripts/run_pkg_tests.sh` | `PASS: cpu_control_pkg compatibility` | 0 |
| 2 | `./scripts/run_base_tests.sh` | `PASS: base datapath modules` | 0 |
| 3 | `./scripts/run_lsu_tests.sh` | `PASS: LSU and address decoder` | 0 |
| 4 | `./scripts/check_control_pkg_compat.sh` | `PASS: M Control compiles with Datapath cpu_control_pkg` | 0 |

四项均通过实际命令执行：

```powershell
& 'C:\msys64\usr\bin\bash.exe' -lc 'export PATH=/ucrt64/bin:/usr/bin:$PATH; cd /d/FPGA/CPU/face_recognition_soc; ./scripts/<对应脚本>'
```

基础测试额外在调用前把 `TMPDIR/TMP/TEMP` 指向 `$PWD/build/tmp`；各新增脚本内部已完成该设置。

首次新增测试编译退出码为 1：Verilator 指出了字节选择的宽度截断、默认 BASE 比较恒真和预期的共享 package unused 参数。宽度与范围表达式均从 RTL 根因修正；最终新增测试没有 RTL warning。`run_lsu_tests.sh` 仅局部关闭共享 package 在该测试中预期的 `UNUSEDPARAM`，其他 lint 保持启用且 fatal。

## 10. 剩余警告和限制

- package/基础回归仍有已记录的 `UNUSEDPARAM`，因为共享接口符号不可能在每个单元测试全部使用。
- 基础回归仍报告既有 `imm_gen.instr[6:0]` 未使用；未修改该既有模块。
- 生成 C++ 时 UCRT 与 Verilator 头文件报告 `STDOUT_FILENO/STDERR_FILENO` 重定义；属于工具链警告，不是 RTL warning。
- Control 兼容脚本继续局部忽略其已记录的 `UNUSEDSIGNAL/UNUSEDPARAM`；不代表真实联调。
- Git 在本环境不可用，未安装。
- 本阶段没有测试 SRAM 时钟沿、总线握手、MMIO 副作用、流水 valid/flush 门控、真实 Control 或真实 CNN。
