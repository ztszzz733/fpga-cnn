# 固定一周期同步 IMEM Fetch Adapter

日期：2026-09-15  
状态：第四步模块与逐时钟单元测试完成；尚未接入完整 `cpu_datapath`。

## 1. 模块职责

`fetch_adapter` 向无 ready 的固定一周期同步 IMEM 发请求，保存请求 PC/PC+4，将延迟返回的指令与元数据配对；IF/ID 暂停时保存一项响应；flush/reset 时使错误路径的在途及缓存响应失效。它不实例化 PC 或 IF/ID，不计算 redirect 目标，也不包含译码、Data SRAM 或 CNN MMIO。

## 2. 正式端口表

| 端口 | 方向 | 位宽 | 含义 |
|---|---|---:|---|
| `clk` | input | 1 | 上升沿时钟 |
| `rst_n` | input | 1 | 同步低有效复位 |
| `request_pc` | input | 32 | 外部 PC 通路当前请求地址 |
| `pc_en` | input | 1 | C1 PC 推进许可 |
| `if_id_en` | input | 1 | C1 IF/ID 消费许可 |
| `flush` | input | 1 | C1 `if_id_flush`/redirect 清除 |
| `imem_addr` | output | 32 | 等于 `request_pc` |
| `imem_re` | output | 1 | 本周期有效请求 |
| `imem_rdata` | input | 32 | IMEM 固定一周期返回字 |
| `fetch_valid` | output | 1 | 当前响应可供 IF/ID 使用 |
| `fetch_instr` | output | 32 | 配对指令 |
| `fetch_pc` | output | 32 | 配对请求 PC |
| `fetch_pc4` | output | 32 | 配对的 32 位自然回绕 PC+4 |

未增加调试端口、`imem_ready` 或可变延迟握手。

## 3. 固定一周期 IMEM 契约

周期 N 内 `imem_re/address` 稳定，末端上升沿由 IMEM 采样；该沿的 NBA 更新后，周期 N+1 的 `imem_rdata` 对应该请求。adapter 在同一沿把请求 valid、PC 和 PC+4写入 `req_*_q`。因此沿后组合旁路把新的 `imem_rdata` 与新的请求元数据配成一组，下一上升沿由未来 IF/ID 消费。

测试 IMEM 使用 `always_ff @(posedge clk)` 和非阻塞赋值，仅在 `imem_re` 时执行 `imem_rdata <= instruction_for(imem_addr)`；不同 PC 返回 `32'hA5A5_0000 ^ PC`，不是组合 ROM或相同 NOP。

## 4. 请求条件

```text
imem_re = rst_n && !flush && pc_en && if_id_en
imem_addr = request_pc
```

C1 正常时两个 enable 同为 1；load-use 时同为 0。暂停不发请求，因此不会反复请求被保持的 PC。buffer 在恢复沿被消费时可以同时发下一请求，保持吞吐。

## 5. 响应配对与内部状态

内部状态：

- `req_valid_q`, `req_pc_q`, `req_pc4_q`：最近已被 IMEM 采样的请求元数据。
- `buffer_valid_q`, `buffer_instr_q`, `buffer_pc_q`, `buffer_pc4_q`：IF/ID 不能消费时保存的一项完整响应。

buffer 有效时输出 buffer；否则 `req_valid_q` 有效时直接输出 `imem_rdata + req_pc_q + req_pc4_q`；无有效响应、flush 或 reset 时全部输出为确定零且 `fetch_valid=0`。

## 6. 响应缓存与暂停

若当前存在直接响应且 `if_id_en=0`，该响应在下一个上升沿进入 buffer，同时 `imem_re=0` 使 `req_valid_q` 清零。暂停持续期间不发请求，buffer 所有字段保持。恢复沿 IF/ID 消费 buffer，buffer 清零；同一沿允许采样新请求，新响应在沿后成为直接输出，因此不会引入额外隔拍气泡或重复旧响应。

一项 buffer 足够：正常时每拍响应都在下一沿消费；暂停开始时最多只有一个直接响应，它被移入 buffer，同时停止新请求；buffer 满时始终没有在途响应；恢复沿清 buffer 并建立至多一个新在途响应。测试通过层次状态和事务 scoreboard 断言 `buffer_valid_q && req_valid_q` 永不同时成立，防止静默覆盖。

## 7. Flush、reset 与优先级

优先级为同步 reset > flush >正常状态更新。组合请求/响应还由 `rst_n && !flush` 立即门控。

- flush：`imem_re=0`、`fetch_valid=0`；在上升沿清除 req 和 buffer 的 valid及全部保存字段。外部负责同时/随后把 redirect 目标装入 PC；flush 解除后才从新的 `request_pc` 发请求。
- reset：行为与 flush 清状态相同且优先；测试保持至少两个上升沿。reset 历史地址不能在释放后生成伪响应。
- flush 与暂停同时出现时仍清除所有旧状态，不执行缓存、消费或请求。

## 8. 逐沿正常取指示例

| 时刻 | 沿前/沿动作 | 沿后结果 |
|---|---|---|
| E0 前 | `imem_re=1, addr=P0` |  |
| E0 | IMEM 采样 P0；adapter 保存 P0/PC4 | `rdata=I(P0)`，直接输出 P0 响应 |
| E1 | IF/ID 消费 P0；同时采样 P1 | 沿后直接输出 P1 响应 |
| E2 | IF/ID 消费 P1；同时采样 P2 | 沿后直接输出 P2 响应 |

初始填充后每个周期一条，没有每两拍一个响应的降吞吐。

## 9. 逐沿暂停示例

| 时刻 | 控制/动作 | 状态 |
|---|---|---|
| E0 后 | P0 返回，随后检测 load-use，两个 enable 拉低 | P0 是未消费直接响应 |
| E1 | IF/ID 保持；adapter 把 P0 响应存 buffer；不发请求 | buffer=P0，req valid=0 |
| E2 | 暂停继续 | buffer P0 全字段保持，不请求 |
| E3 | 暂停解除；IF/ID 消费 P0；同时请求 P1 | buffer 清除，沿后直接输出 P1 |

单周期暂停和连续至少三周期暂停均按此行为通过测试。

## 10. 逐沿 flush 示例

| 时刻 | 控制/动作 | 状态 |
|---|---|---|
| E0 后 | 旧路径 Pold 响应在途或已进入 buffer | 旧响应尚未提交 |
| E1 前/沿 | `flush=1`，旧路径响应不得被 IF/ID消费 | 请求关闭；req/buffer 全清 |
| E1 后 | 外部 PC 已/将更新为目标 T | `fetch_valid=0` |
| E2 | flush 解除，请求 T | 沿后只出现 T 的响应 |

直接在途响应 flush 和已缓存响应 flush 两种场景都由 scoreboard 证明旧 PC 不再交付。

## 11. NBA 语义

IMEM 与 adapter 都在同一上升沿使用非阻塞赋值。任何 `always_ff` 在该沿执行时看到的都是沿前值；全部 NBA 完成后，组合输出才看到新的 `imem_rdata` 与新的 `req_*_q`。因此设计不在同一 `always_ff` 中错误采样“刚更新”的 IMEM 数据：正常返回走沿后组合旁路；需要暂停时，下一沿才把已经稳定一个完整周期的响应写入 buffer。测试 scoreboard 在目标采样沿前检查 IF/ID 将看到的值，避免依赖进程执行顺序。

## 12. 未来顶层连接

- `request_pc` 接 PC 寄存器输出，`pc_en/if_id_en` 接 C1 同名控制。
- `flush` 接 `if_id_flush`；redirect target仍由外部 next-PC MUX装入 PC。
- `fetch_valid/instr/pc/pc4` 接现有 `if_id_reg` 的对应输入。
- IF/ID 的 `en=if_id_en`、`flush=if_id_flush`，保持其 reset/flush > enable > hold 规则。
- 顶层不得把 `fetch_valid` 当成可变延迟 ready，也不得绕过 adapter 使用组合 IMEM。

## 13. 测试覆盖与结果

`tb_fetch_adapter.sv` 覆盖：两沿 reset及伪响应排除；RESET_PC 0首条取指；连续8个不同地址的一拍吞吐；单周期暂停；至少三周期暂停及 buffer 字段保持；无在途请求暂停；在途/直接响应 flush；buffered response flush；flush+暂停；reset+flush+enable；`0xFFFF_FFFC+4` 回绕；48周期交替正常、1～3拍暂停、三次 flush和新目标的压力序列。

事务 scoreboard 记录每个 `imem_re` 接受请求，只有 `if_id_en && fetch_valid && !flush && rst_n` 才出队；检查每项最多交付一次、顺序、PC/指令/PC4配对、flush 队列失效、无未知来源响应和最终排空。最终无断言失败。

最终代码状态下先清理且只清理 `build/pkg`、`build/base_modules`、`build/lsu`、`build/fetch`、`build/control_pkg_compat`，再按顺序执行：

| 顺序 | 脚本 | PASS | 退出码 |
|---:|---|---|---:|
| 1 | `./scripts/run_pkg_tests.sh` | `PASS: cpu_control_pkg compatibility` | 0 |
| 2 | `./scripts/run_base_tests.sh` | `PASS: base datapath modules` | 0 |
| 3 | `./scripts/run_lsu_tests.sh` | `PASS: LSU and address decoder` | 0 |
| 4 | `./scripts/run_fetch_tests.sh` | `PASS: fetch adapter` | 0 |
| 5 | `./scripts/check_control_pkg_compat.sh` | `PASS: M Control compiles with Datapath cpu_control_pkg` | 0 |

实际调用形式：

```powershell
& 'C:\msys64\usr\bin\bash.exe' -lc 'export PATH=/ucrt64/bin:/usr/bin:$PATH; cd /d/FPGA/CPU/face_recognition_soc; ./scripts/<对应脚本>'
```

首次 fetch lint 退出码 1，原因仅在新 TB：边沿 scoreboard 使用阻塞赋值和 `imem_rdata` 初始化造成多驱动。scoreboard 改为采样沿前显式参考任务，并移除第二驱动后，最终 lint、构建和仿真均通过；DUT 未因此改变接口或时序方案。

## 14. 剩余警告与限制

- fetch 最终构建无 SystemVerilog lint warning；生成 C++ 时仍有 Verilator 5.050/UCRT 头文件 `STDOUT_FILENO/STDERR_FILENO` 重定义工具链警告。
- 基础回归仍有既有 `imm_gen` unused bits 与共享 package unused parameter 警告；本步骤未修改相关文件。
- Control package 兼容脚本保留已记录的局部 unused 类别抑制。
- 固定延迟契约没有 `imem_ready`，不支持缺响应、多周期或可变延迟 IMEM。
- 本阶段未实现独立 IMEM model正式文件、PC/IF-ID实际顶层接线、Control stub、完整译码、Data SRAM、CNN MMIO 或真实集成。
- Git 在当前环境不可用，未安装。
