# CPU Control 与 B1 存储器/CNN 对接基线审计

日期：2026-09-28  
审计范围：`rtl/common`、`rtl/cpu_control`、Control文件清单、test-only接线stub、驱动示例及当前接口文档  
对照基线：[CNN负责人交接说明](cnn_developer_handoff_B_port_v1.md)、[Datapath负责人交接说明](datapath_developer_handoff_memory_v1.md)、根目录原始三方分工规格

## 1. 结论

**生产CPU Control RTL与2026-09-28 B1基线没有功能出入，不需要修改生产端口、编码或逻辑。**

B口、仲裁器、双口SRAM、CNN MMIO寄存器组和图像桥均位于Control边界之外。Control继续保持48个C1端口和组合逻辑，不增加`b_*`、`cnn_mem_*`、`STATUS`或`CONTROL`直连端口。

本轮改正的是过期的测试注释和当前接口说明，不修改7个生产Control文件，因此不会改变C1共享编码或生产RTL哈希。

## 2. 逐模块核查

| 文件/模块 | 核查内容 | 结果 | 处理 |
|---|---|---|---|
| `cpu_control.sv` | 48端口、组合逻辑、无CNN/SRAM状态 | 符合 | 不修改 |
| `main_decoder.sv` | RV32I Load/Store、非法指令安全NOP | 符合 | 不修改 |
| `alu_decoder.sv` | RV32I算术与完整funct合法性 | 符合 | 不修改 |
| `hazard_unit.sv` | 一拍load-use、禁止MEM Load地址前递 | 符合固定一周期A口契约 | 不修改 |
| `branch_control.sv` | EX级分支/JAL/JALR重定向 | 符合 | 不修改 |
| `pipeline_control.sv` | reset > redirect > load-use > 正常 | 符合 | 不修改 |
| `cpu_control_pkg.sv` | C1唯一编码来源 | 符合且必须保持哈希稳定 | 不修改 |
| `cpu_control_link_example.sv` | stub接线注释 | 旧注释错误地说真实Datapath联调未运行 | 已改正 |
| `control_datapath_stub.sv` | RESET_PC注释 | 旧注释只写D1建议值 | 已标注B1开发基线值 |
| `cnn_driver_example.c` | start/status约定说明 | 旧注释仍写待冻结 | 已指向B1交接语义 |
| `cpu_control_interface.md` | 地址、写提交边沿、B口描述 | 存在历史措辞与当前基线并列造成的歧义 | 已改正 |

## 3. 为什么Control不增加B口接口

原始三方职责规定：

- Control只输出指令控制和流水线选择；
- Datapath根据Load/Store控制生成CPU A口事务；
- CNN memory master生成CNN侧70位B口请求；
- `sram_b_arbiter`选择CNN或图像桥并返回35位响应。

实际关系为：

```text
CPU Control ──C1控制──▶ CPU Datapath ──dmem_*──▶ SRAM A口

CNN memory master ─┐
                   ├──▶ sram_b_arbiter ──▶ SRAM B口
image_io_bridge ───┘
```

如果把B口握手接进Control，会让Control承担跨周期请求状态，违反“Control组合逻辑、跨级状态由Datapath/外设持有”的项目约定。

## 4. 访存提交边沿

当前生产Datapath已经实际验证的行为是：

- Data SRAM请求在EX→MEM上升沿提交；
- Load数据在随后的MEM周期稳定，并在MEM→WB沿保存；
- CNN MMIO写在MEM级提交；
- Control只产生D级`memread_d/memwrite_d`和类型控制，不直接产生实际SRAM/MMIO写使能。

因此不能再统一写成“SRAM和MMIO均由`valid_m && memwrite_m`提交”。两条路径必须分别描述。

## 5. B1参数与回签状态

| 参数 | B1开发值 | 状态表述 |
|---|---:|---|
| `RESET_PC` | `0x0000_0000` | 用户确认的B1开发值；等待D/Z回签归档 |
| `SRAM_BASE` | `0x0000_0000` | B1开发值 |
| `SRAM_SIZE` | `0x0004_0000` | B1开发值，实体板资源仍待验证 |
| `CNN_MMIO_BASE` | `0x4000_0000` | B1开发值，与生产Datapath默认值一致 |
| `CNN_MMIO_SIZE` | `0x0000_1000` | B1开发值 |
| B口请求 | 70 bit | 用户确认，D/Z待回签和实现 |
| B口返回 | 35 bit | 用户确认，包含不可删除的error |

“开发值已确定”和“其他负责人已经接受并完成RTL”是两件事。当前文档使用前一种表述，不把未收到的D/Z回签写成已完成。

## 6. Control侧保持不变的约束

- 48个C1端口、方向和位宽不变；
- `cpu_control_pkg.sv`数值编码不变；
- Control不持有PC、流水寄存器、SRAM或CNN寄存器；
- `rst_n=0`时组合输出安全值；
- RV32I基线不实现M/Zmmul，`mul_busy`非零不在支持域；
- 不增加CNN专用状态机；CNN Driver仍是普通MMIO软件；
- 不因B口增加CPU流水线ready/stall端口；
- 实体A口若不能满足固定一周期，必须升级系统接口，不能私改Control。

## 7. 验证结果

文档改正后已重新运行：

```powershell
python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot
```

结果为 **PASS**：Vivado XSim 2026.1完成编译、展开和仿真，共1,244个场景、30,463项检查、0失败；其中包含55条定向译码、1,000条随机译码以及128组随机冒险状态。四组PNG/SVG波形均由本次独立运行生成，编译和仿真日志未发现`WARNING`、`ERROR`或`FATAL`行。

本次证据：[result.json](../build/runs/20260928_215503_605664_7528_all_seed1/result.json)、[编译日志](../build/runs/20260928_215503_605664_7528_all_seed1/compile.log)、[仿真日志](../build/runs/20260928_215503_605664_7528_all_seed1/simulation.log)、[完整VCD](../build/runs/20260928_215503_605664_7528_all_seed1/waves/cpu_control.vcd)。7个生产Control/package文件与`verification_manifest.json`中的基线哈希逐一比对，全部未变化。

由于项目中仍没有B口仲裁器、双口SRAM或CNN memory master的生产RTL，本次Control回归不能替代后续仲裁器、双口SRAM和CNN联调。
