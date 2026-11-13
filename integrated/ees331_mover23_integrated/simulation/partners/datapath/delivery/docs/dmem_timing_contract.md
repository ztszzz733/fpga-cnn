# 固定一周期 Data SRAM 时序契约

验证日期：2026-09-15。此文档描述仿真模型和后续 Datapath 的候选接口，不代表实体 FPGA BRAM 或 CNN 集成已经验证。

## 1. 模型端口与存储规则

`dmem_model #(MEM_BYTES=262144)` 的实际端口为 `clk`、`re`、`we`、`wstrb[3:0]`、`addr[31:0]`、`wdata[31:0]` 和 `rdata[31:0]`。默认容量为 256 KiB，合法字节地址是 `0x0000_0000..0x0003_FFFF`。

模型是 32 位、小端、单 CPU 地址端口。`wstrb[n]` 控制对齐字中第 n 个字节，`wdata[8*n +: 8]` 写入该 lane。测试平台可用层次名 `u_mem.mem[index]` 初始化和检查 byte array。模型没有 CNN B 口、MMIO、ready、可变等待或厂商 BRAM 原语。

越界读确定返回零，越界写无副作用。`rdata` 在首次请求前也为确定零；`re=0` 时保持上次确定值，绝不主动输出 X。同沿读写同一位置按 SystemVerilog NBA 读取沿前旧内容；当前 CPU 接口不会对同一指令同时拉高读写。

## 2. 固定一周期同步读和 NBA

周期 N 内保持 `re=1` 和地址；周期 N 结束的上升沿采样请求；该沿所有 `always_ff` 先读取旧 `rdata`，随后 NBA 更新 `rdata`。因此数据在该沿后、随后的整个周期稳定。另一个在同一沿执行的 `mem_wb_reg` 不能看到“刚更新”的数据。

TB 的 `observed_at_edge` 与 SRAM 都使用 `always_ff`。每次读都断言：沿的活动区 `rdata` 仍为旧值；沿后为新字；观察寄存器仍捕获旧值。这是实际逐沿断言，不是组合查表替代。

## 3. M 级请求实验（方案 A）

先让 SRAM 返回地址 0 的 `0x11111111`，下一拍令 M 级请求地址 4 的 `0x22222222`。M→W 同沿后，观察寄存器是 `0x11111111`，而 SRAM `rdata` 才变为 `0x22222222`。结论：M 级才发固定一周期同步读时，现有 `mem_wb_reg` 会抓旧数据；方案 A 不兼容。

## 4. EX 级请求实验（方案 B）

EX 周期给出 load 地址、`re` 和元数据；EX→M 沿 SRAM 采样旧 E 地址，同时 `ex_mem_reg` 保存同一 load 的地址、`rd`、`regwrite`、`load_type` 和 `wb_sel`。沿后读字在整个 M 周期稳定，现有 `lsu` 用 M 级地址低位/type完成抽取，M→W 沿由 `mem_wb_reg` 保存处理结果。

仿真实例得到 `rd=5`、`regwrite=1`、`wb_sel=WB_LOAD`、地址 100、数据 `0x12345678`，全部属于同一条 load。随后模拟消费者通过 WB 前递加 7，得到 `0x1234567F`。这与 C1 的一拍 load-use 气泡吻合，无须第二拍 stall。

## 5. E0～E3 逐沿说明

令 L 为 load，C 为立即使用 L 的消费者；旧值为 SRAM 上一笔返回。

| 时段/沿 | E 级 | M 级 | addr / re / we | SRAM rdata | MEM/WB 采样 |
|---|---|---|---|---|---|
| E0 前 | L，地址 A | 旧指令 | A / 1 / 0 | 旧值 | 尚未采样 L |
| E0 后 | 气泡将进入 E | L | 新 E 请求关闭 | `Mem[A]` | 旧 M 指令；L 元数据已在 M |
| E1 前 | 气泡 | L | 无请求 | `Mem[A]` 稳定 | 将采样 LSU(`Mem[A]`, A低位, type L) |
| E1 后 | C 可进入 E | 气泡 | 下一条访问可发 | 保持或下一请求返回 | W=L，数据和 rd/regwrite/wb_sel配对 |
| E2 后 | C 用 `FWD_WB` 完成 | 后续 | 后续 | 后续 | L 可写回/前递 |
| E3 后 | 后续 | C | 后续 | 后续 | 正常推进 |

对 store，地址、已完成 `fwd_store` 的数据和 strobe 在 E 周期稳定，并在 EX→M 沿写入。store 没有延后到 M 才产生副作用。

## 6. 单端口结构冲突

若采用“load 在 E 请求、store 在 M 提交”的混合方案，同周期 M-store 地址 `0x80` 与 E-load 地址 `0x100` 需要两个不同地址；标准单端口只有一个 `addr`，不能同时完成。选择任一地址都会丢 load 或丢 store。解决这种混合方案只能增加独立读/写地址通道、额外 CPU 读端口，或引入 stall/arbitration。

本次选择所有 CPU 数据访问都在 EX→M 边界提交：E 每周期最多一条指令，所以最多一个 load 或 store 请求；连续 load、store→load、load→store、连续 store均无 M/E 双请求。此方案使用现有单端口，不需要额外读端口、双地址通道或 memory stall。

提前提交 store 是安全的前提：地址和经 `fwd_store` 选择的数据在 E 已稳定；写使能必须是 `rst_n && valid_e && memwrite_e && sram_hit && store_type_valid && store_aligned`；redirect 在 EX 解析时只冲刷更年轻的 D/IF 指令，当前 E 指令不是错误路径且应提交；reset、invalid、被更早 redirect 清出的气泡均不得写。TB 验证 valid=0、模拟错误路径和 reset 门控均无写入。

## 7. 六种候选方案比较

| 方案 | 同步一周期 | 现有 MEM/WB | C1 一气泡 | 连续 load | M-store/E-load | 改 C1 | 当前外部接口结论 |
|---|---|---|---|---|---|---|---|
| A：M 发 read，M→W 同沿采样 | 是 | 否，抓旧值 | 否 | 请求可连续但数据错配 | store占同一端口 | 否 | 淘汰 |
| B：EX 发 read，M 接收 | 是 | 是 | 是 | 是 | 若 store也在 EX则不存在 | 否 | **采用，并扩展为所有访问在 EX提交** |
| C：EX-read、M-store共用单端口 | 是 | load兼容 | load本身兼容 | 是 | 否，双地址冲突 | 否 | 淘汰 |
| D：独立读写地址通道 | 是 | 是 | 是 | 是 | 是 | 否 | 可行但接口/存储结构更复杂，当前不需要 |
| E：增加 ready/stall | 可支持 | 需改寄存器保持 | 可能增加气泡 | 可支持 | 可仲裁 | **是** | 当前禁止采用 |
| F：组合读 | **否** | 表面可用 | 表面可用 | 是 | 仍可能冲突 | 否 | 明确禁止 |

## 8. 覆盖结果

`tb_dmem_timing.sv` 实例化现有 `lsu.sv`，没有复制 load/store 算法。测试覆盖：单 LW；连续不同地址 LW；LW 后立即使用（WB 前递值）；同址与异址 SW→LW；LW→SW；连续 SW；LB 四 lane；LH 两 lane；LBU/LHU；SB 四 lane；SH 两 lane；SW 四字节；非对齐 load/store；首地址；末尾合法字；越界读写；valid=0 store；模拟错误路径 store；reset store；同沿 NBA 与 MEM/WB 顺序。所有断言通过。

连续访问结果包括 load→load、store→load、load→store、store→store；byte enable和小端组合均通过。M-store/E-load 的不同双地址实验确认混合分级在单端口不可表达，而统一 EX 提交消除了该组合。

## 9. 后续顶层必须遵守

推荐 CPU 侧 Data SRAM 端口保持模型同构：`dmem_addr[31:0]`、`dmem_wdata[31:0]`、`dmem_wstrb[3:0]`、`dmem_re`、`dmem_we`、`dmem_rdata[31:0]`；无 ready。

- 在 E 级产生并门控 `re/we/addr/wdata/wstrb`，在 EX→M 沿由 SRAM 接受。
- load 的地址低位、type、rd、regwrite和 wb_sel 经现有 EX/MEM 保持；M 级以同步返回字和这些元数据驱动 LSU；M→W 沿保存最终 load 数据。
- store 数据必须先完成 `fwd_store`；所有副作用用 `rst_n && valid_e` 及合法/命中/对齐条件门控。
- 不得同时从 M 再发 store，不得把同步 SRAM 改成组合读，不得暗加 ready，也不得让 MMIO 沿用未经单独证明的同步 SRAM 时序。
- 一拍 load-use 后，消费者在 E 从 W 前递；EX/MEM 和 MEM/WB继续每拍推进。

该方案不修改 C1 接口，也不修改任何既有生产 RTL。剩余风险是实体 FPGA SRAM wrapper 的 read-during-write模式、综合初始化和物理时序尚未验证；CNN MMIO 与共享 SRAM B 口不在本模型范围。

## 10. 实际命令与验收

命令：`./scripts/run_dmem_timing_tests.sh`。最终输出 `PASS: fixed-latency Data SRAM timing`，退出码 0。Verilator/SystemVerilog lint无告警；生成 C++ 有 UCRT `STDOUT_FILENO`/`STDERR_FILENO` 重定义工具链告警。

最终干净构建回归记录：

| 顺序 | 脚本 | PASS | 退出码 | 警告 |
|---:|---|---|---:|---|
| 1 | `run_pkg_tests.sh` | `PASS: cpu_control_pkg compatibility` | 0 | 无新增 SV 告警 |
| 2 | `run_base_tests.sh` | `PASS: base datapath modules` | 0 | 既有 base/package unused 类告警按原脚本处理 |
| 3 | `run_lsu_tests.sh` | `PASS: LSU and address decoder` | 0 | 仅 UCRT 生成 C++ 宏重定义 |
| 4 | `run_fetch_tests.sh` | `PASS: fetch adapter` | 0 | 仅 UCRT 生成 C++ 宏重定义 |
| 5 | `run_dmem_timing_tests.sh` | `PASS: fixed-latency Data SRAM timing` | 0 | 仅 UCRT 生成 C++ 宏重定义 |
| 6 | `check_control_pkg_compat.sh` | `PASS: M Control compiles with Datapath cpu_control_pkg` | 0 | 兼容脚本保留已记录的局部 unused 抑制 |

第 4 项脚本完成干净重建后，批处理输出通道被执行器截断；为取得明确终态，又直接执行该次新生成的 `build/fetch/Vtb_fetch_adapter.exe`，再次得到相同 PASS 和退出码 0。其余项目均从对应脚本取得退出码。

结论：第五步验收通过，可以按已验证的存储时序搭建cpu_datapath顶层。
