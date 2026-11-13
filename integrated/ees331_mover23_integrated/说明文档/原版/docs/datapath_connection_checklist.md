# 收到真实 Datapath 后的连接清单

当前状态：**D1 原则接受 C1，Control 项目已对齐；公共参数/存储时序待冻结，真实 Datapath 直连未运行**。连接样例中的模块明确名为 control_datapath_stub。结构编译通过不等于真实 CPU 行为兼容。详见 [D1 对齐记录](control_reply_to_D1.md)。以下勾选框用于未来真实 RTL 验收，不能用原则接受替代实测。

- [ ] 与负责人逐项核对 cpu_control_interface.md 的全部端口名、宽度、方向和复位值；C1 新增端口需实际生产者，不能绑常量冒充。
- [ ] rs1_d/rs2_d 对应有效 instr_d 的 [19:15]/[24:20]。
- [ ] rs1_e/rs2_e、uses_rs1/2_e、branch_type_e、jump_e 都由同一条 ID/EX 指令产生。
- [ ] valid_d/e/m/w 由 Datapath 保存；rd、regwrite、memread 同级且同周期。
- [ ] alu_ctrl/ALUSrc 等 D 输出先进入 ID/EX，M/W 所需控制继续流水；不得直连当前 EX ALU 或 MEM LSU。
- [ ] 前递 A/B 先于 ALUSrc MUX；Branch 比较用前递值；Store 的前递 rs2 保存到 EX/MEM.WriteData。
- [ ] M 前递为非 Load 最终结果，JAL/JALR 为 PC+4；W 前递为 WB MUX 最终值，包括 Load。
- [ ] MEM Load 屏蔽旧 WB 同名值；合法程序不能在该状态消费。
- [ ] 按 D1 实现显式 WB→ID 旁路：valid_w && regwrite_w && rd_w!=0 且源编号匹配时取最终 wb_data，并有同周期同址测试证明。EX 前递无法修复已经离开 W 的旧读值。
- [ ] reset > flush > enable；冲刷清 valid、写/访存/branch/jump；旧 E 正常进入 M，JAL 链接保留；Store 只提交一次。
- [ ] x0 恒零、非零 rd 才实际写寄存器；实际写存储器与 valid_m、实际写寄存器与 valid_w 相与。
- [ ] JALR 使用 `(forwarded_rs1_e+imm_e)&~1`；Branch/JAL 使用 pc_e+imm_e。
- [ ] memory_timing_contract.md 的 M→W 数据边沿成立；不成立则补接口，不改个延迟数字草率兼容。
- [ ] 同步 IMEM wrapper 在 stall/redirect 时保持 PC/指令配对并丢弃错误返回。
- [ ] mul_busy=0；未来多周期操作需完整完成握手及各级保持规则。
- [ ] CNN 的九个 32 位端口只在 Datapath/CNN 边界；start W1P、done/error 粘滞、STATUS RO 和地址映射另行联调。
- [ ] CNN 参数位域、MMIO 基地址、数据对齐和非法策略经团队确认并版本化。
- [ ] 共用唯一 cpu_control_pkg.sv，先于双方 RTL 编译；核对文件归属及共享版本，禁止各自维护不同编码副本。
- [ ] RESET_PC 参数默认零的建议和同步低有效复位经系统三方确认；检查实际入口 PC 和首条返回指令配对。
- [ ] LB/LBU/SB 任意字节、LH/LHU/SH 2 字节对齐、LW/SW 与 CNN 张量基地址 4 字节对齐；执行程序不含未支持访问。
- [ ] 非法/FENCE/ECALL/EBREAK 安全 NOP 无架构副作用；真实流水需检查提交、Store 和重定向。
- [ ] Datapath CPU 使用 SRAM A 口，CNN DMA 使用 B 口；真实 MMIO 检查 start/soft_reset 单周期脉冲、STATUS 写无效。
- [ ] 将 cpu_control_link_example 的 stub 换为真实实例，保留逐端口 `.port(signal)`，编译后运行真实程序、访存和提交检查。

如果实际接口不同，先给逐项差异/适配补丁，由生产模块负责人采用；本次没有可供补丁对比的真实 Datapath 文件。
