# 说明文件目录

第一次使用，先看 [运行教程](README_TEST.md)；想理解代码，再看 [代码阅读指南](module_map.md)。不用一次读完所有文件。

## 日常使用

| 文档 | 什么时候看 |
|---|---|
| [运行教程](README_TEST.md) | 第一次跑测试、找结果、看图片或遇到报错 |
| [代码阅读指南](module_map.md) | 想知道各个代码文件做什么 |
| [本次对接说明](control_reply_to_D1.md) | 想了解按对方文档改了什么、还有什么没确定 |
| [验证报告](verification_report.md) | 需要查看实际测试记录和验证范围 |

## 需要深入时再看

这些文件保留精确的参数和信号名，供修改测试、接线和排查问题时查询。

| 文档 | 内容 |
|---|---|
| [换电脑与高级用法](TEST_REFERENCE.md) | 工具准备、测试参数、添加用例、波形设置 |
| [接口说明](cpu_control_interface.md) | 控制模块与数据通路之间每根信号怎么连接 |
| [存储时序说明](memory_timing_contract.md) | 什么时候请求数据、什么时候必须拿到数据 |
| [暂停与结果传递规则](hazard_forward_table.md) | 指令互相依赖时如何处理 |
| [接入检查清单](datapath_connection_checklist.md) | 收到真实数据通路代码后逐项检查 |
| [指令译码表](decode_table.csv) | 每种指令对应的控制输出 |
| [接口审计](interface_audit.md) / [变更记录](interface_change_log.md) | 设计选择的原因与历史变化 |

## 原始资料

- [SoC 原始规格](../face_recognition_soc_spec_v0.1.md)：整个系统的设计要求。
- [Control 原始任务书](../CPU_CONTROL_Codex_代码生成提示词.md)：控制模块最初的实施要求。
- [Datapath 回复原文](inputs/CPU-DP-IF-D1.md)：对方对接口方案的回复，原文保留。

文档中出现的 **Control** 指控制模块，**Datapath** 指负责保存和运算数据的部分。**C1** 是控制侧接口方案的编号，**D1** 是对方回复的编号；运行测试时不需要设置它们。
