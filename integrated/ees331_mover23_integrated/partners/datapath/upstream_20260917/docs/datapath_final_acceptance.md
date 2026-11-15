# CPU Datapath 最终独立验收报告

验收日期：2026-09-16  
工具：Verilator 5.050 2026-07-01 rev vUNKNOWN-built20260702  
结论：通过，可作为独立Datapath模块交付；本次不是M方Control、Z方CNN或三方SoC真实联调。

## 1. 项目范围

本次只执行只读审查、静态接口冻结、全新构建回归、生产RTL哈希复核和交付打包。没有增加CPU功能，没有修改既有RTL/TB/model/单项脚本，没有实例化真实Control/CNN，也没有创建SoC或双口SRAM。

## 2. 最终生产RTL与filelist

正式filelist为 `rtl/filelists/cpu_datapath.f`，按依赖顺序且每项只出现一次：

1. `rtl/common/cpu_control_pkg.sv`
2. `rtl/cpu_datapath/alu.sv`
3. `rtl/cpu_datapath/imm_gen.sv`
4. `rtl/cpu_datapath/pc.sv`
5. `rtl/cpu_datapath/regfile.sv`
6. `rtl/cpu_datapath/if_id_reg.sv`
7. `rtl/cpu_datapath/id_ex_reg.sv`
8. `rtl/cpu_datapath/ex_mem_reg.sv`
9. `rtl/cpu_datapath/mem_wb_reg.sv`
10. `rtl/cpu_datapath/address_decoder.sv`
11. `rtl/cpu_datapath/lsu.sv`
12. `rtl/cpu_datapath/fetch_adapter.sv`
13. `rtl/cpu_datapath/cpu_datapath.sv`

filelist不含TB、stub、model、build、M/Z RTL或第二份package。以 `cpu_datapath` 为顶层的Verilator lint退出0，无生产RTL错误。

## 3. Test-only文件

- 模型：`tb/models/control_stub.sv`、`imem_model.sv`、`dmem_model.sv`、`cnn_mmio_stub.sv`
- 单元TB：`tb/unit/tb_cpu_control_pkg.sv`、`tb_base_modules.sv`、`tb_lsu_address_decoder.sv`、`tb_fetch_adapter.sv`、`tb_dmem_timing.sv`
- 集成TB：`tb/integration/tb_cpu_datapath.sv`

这些文件不属于生产filelist。Control/CNN stub仅用于验证接口行为，不替代M/Z生产RTL。

## 4. 顶层参数和端口分类

参数为 `RESET_PC=0x00000000`、`SRAM_BASE=0x00000000`、`SRAM_SIZE=0x00040000`、`CNN_MMIO_BASE=0x40000000`、`CNN_MMIO_SIZE=0x1000`。

端口分为：`clk/rst_n`；C1 48端口中的24个Datapath→Control、22个Control→Datapath及两个公共端口；固定一周期IMEM三信号；固定一周期Data SRAM六信号；CNN CPU侧MMIO六信号。完整逐项定义见 `docs/cpu_datapath_interface.md`。

## 5. C1接口冻结检查

`scripts/check_c1_interface.sh`只读解析本工程 `cpu_datapath.sv` 与M方生产 `cpu_control.sv`。48项端口的名称、logic类型、方向和位宽全部匹配；除公共 `clk/rst_n` 同为输入外，Control与Datapath方向逐项相反。脚本不实例化或运行真实Control，结果：`PASS: C1 Control-Datapath interface match`，退出码0。

## 6. CNN MMIO接口冻结检查

`scripts/check_cnn_mmio_interface.sh`直接只读解析现场ZIP中唯一的新版 `mobilefacenet/rtl/mobilefacenet_accelerator_top.sv`。`mmio_addr/wdata/we/re/rdata/ready`六信号方向反向匹配、位宽一致；默认基址 `0x40000000`、窗口4 KiB、九个偏移 `0x00..0x20` 均匹配。Datapath没有误收CNN SRAM Master六信号。结果：`PASS: CNN MMIO CPU-side interface match`，退出码0。

## 7. 存储时序与访问

IMEM是固定一周期同步读，无ready；fetch adapter保存请求PC/PC+4，在stall缓存响应，在flush/reset丢弃错路响应。

Data SRAM是256 KiB小端、4-bit byte enable、固定一周期同步读。所有SRAM load/store在E级产生并在EX→M沿采样/提交；load返回字在M周期与EX/MEM保存的地址低位、load type、rd和WB元数据配对，经LSU抽取后在M→W沿锁存。不得退回M级发read并同沿采新数据的错误方案。

CNN MMIO在M级提交，仅允许九个寄存器的对齐LW/SW。合法请求要求组合 `ready=1`；若违约，C1没有隐藏stall，load取0并由仿真断言报告。M级MMIO与下一条E级SRAM可并行。

## 8. 执行、前递和流水控制

前递优先M级非load，再WB；load地址不作为MEM前递值；store使用独立 `fwd_store`。load-use保持PC/IF-ID并冲刷ID/EX，恰插一个bubble，M/W继续推进。

branch比较使用前递后的寄存器源；Branch/JAL目标为 `pc_e+imm_e`；JALR为 `(src1_fwd_e+imm_e)&0xFFFFFFFE`；JAL/JALR均以PC+4写回。

控制优先级是 reset > redirect > load-use > normal。redirect冲刷年轻IF/D指令，当前E级老指令继续进入M。所有RF/SRAM/MMIO副作用均由相应级valid、reset、命中、类型和对齐条件门控。

## 9. 非法及错误路径处理

非法指令是安全NOP。未映射、窗口内未实现、非对齐、非法类型及MMIO窄访问均确定性返回0或无写副作用，不永久等待。测试覆盖redirect后寄存器、SRAM和MMIO零副作用，reset和valid bubble零副作用，x0恒零。

## 10. 测试覆盖

覆盖共享编码、ALU/立即数/PC/RF/四组流水寄存器、LSU所有lane和对齐、地址边界、防回绕、同步IMEM stall/flush、同步Data SRAM NBA、连续load/store、完整真实机器码五级流水、EX/MEM与MEM/WB前递、WB→ID旁路、一个load-use气泡、六类分支、JAL/JALR、MMIO、非法访问及混合压力程序。详细40类清单见 `docs/cpu_datapath_interface.md`。

## 11. 干净构建与十项结果

验收前记录13个生产RTL SHA-256，只删除工程 `build` 下明确的 `pkg/base_modules/lsu/fetch/dmem_timing/datapath/control_pkg_compat/acceptance/tmp` 子目录，然后执行：

```bash
./scripts/run_all_datapath_tests.sh
```

| # | 步骤 | PASS文本 | 退出码 |
|---:|---|---|---:|
| 1 | package | `PASS: cpu_control_pkg compatibility` | 0 |
| 2 | base | `PASS: base datapath modules` | 0 |
| 3 | LSU/decoder | `PASS: LSU and address decoder` | 0 |
| 4 | fetch | `PASS: fetch adapter` | 0 |
| 5 | Data SRAM | `PASS: fixed-latency Data SRAM timing` | 0 |
| 6 | complete Datapath | `PASS: complete CPU datapath with test stubs` | 0 |
| 7 | Control package兼容 | `PASS: M Control compiles with Datapath cpu_control_pkg` | 0 |
| 8 | C1静态接口 | `PASS: C1 Control-Datapath interface match` | 0 |
| 9 | CNN MMIO静态接口 | `PASS: CNN MMIO CPU-side interface match` | 0 |
| 10 | 正式filelist lint | `PASS STEP: cpu_datapath_filelist_lint (exit 0)` | 0 |

总输出：`PASS: all CPU datapath acceptance checks`；总退出码0。测试前后生产RTL SHA-256逐行完全一致。

## 12. 剩余警告

- `run_base_tests.sh`保留既有 `imm_gen.instr[6:0]` unused和共享package部分 `UNUSEDPARAM`；原脚本以 `-Wno-fatal`记录而不隐藏。
- 完整Datapath与正式filelist lint使用build目录内精确到 `imm_gen.sv` 的规则处理同一既有unused，不是全局关闭lint。
- Control package兼容脚本保留已记录的局部 `UNUSEDSIGNAL/UNUSEDPARAM`抑制。
- Verilator 5.050与UCRT生成C++报告 `STDOUT_FILENO/STDERR_FILENO`宏重定义，不属于RTL告警。

没有未处理的宽度、锁存器、多驱动或接口错误。

## 13. 给M负责人的连接说明

实例化M方生产 `cpu_control`，按48个同名C1端口显式连接 `cpu_datapath`；双方只编译本交付中的唯一 `rtl/common/cpu_control_pkg.sv`，接入前共同确认该文件哈希。不要加入memory ready/stall或改变编码。真实集成后仍须重新跑Control+Datapath程序级回归，本报告不替代该工作。

## 14. 给Z负责人的连接说明

只连接 `mmio_addr/mmio_wdata/mmio_we/mmio_re/mmio_rdata/mmio_ready` 六个CPU侧信号；基址 `0x40000000`，仅九个对齐LW/SW偏移。Z侧合法请求必须组合及时ready。CNN `mem_addr/mem_wdata/mem_read/mem_write/mem_rdata/mem_ready` 属于独立SRAM Master/B口，不能连接到本Datapath MMIO端口。

## 15. 尚未完成与交付判定

尚未完成：真实M方Control连接、真实Z方CNN连接、双口共享SRAM及B口适配、SoC顶层、实体FPGA BRAM/时序、系统复位分发、同址冲突和真实模型软件验证。

当前Datapath生产RTL、接口、test-only验证和交付边界已冻结，满足独立交付条件。明确声明：尚未完成真实Control/CNN联调，也未完成三方SoC联调。
