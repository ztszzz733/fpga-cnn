# 说明文档总目录

**当前交付（2026-09-14 P1）**：[M 正式确认回复](../docs/control_reply_to_P1.md) · [当前 48 端口接口](../docs/cpu_control_interface.md) · [联调序列](../docs/control_datapath_directed_tests.md) · [本次验证](../docs/verification_report.md)。M 已接受 C1 v1.0；三方系统冻结和真实联调仍待完成。docs 中本次更新的文件为当前版本，“说明文档/原版”保留历史。

第一次使用先打开 **[新手版测试教程](新手版/test.md)**。想看项目用途，打开 **[新手版首页](新手版/README.md)**。

## 文件夹怎么分

```text
说明文档/
├── README.md          ← 当前总目录
├── 原版/              ← 完整原说明、精确信号表和原始附件
└── 新手版/            ← 中文解释、操作步骤、实例和对应原版链接
    ├── README.md
    ├── test.md
    └── 其他专题说明
```

原版优先采用上次简化前的备份；当时尚未存在的补充文件采用本次整理前版本。原版正文不改写，仅修正搬移后的文件链接，完整文件来源列在 [整理记录](整理记录.json)。早期草案和任务书中的建议、待办不表示已经完成。

原工程没有单独叫 test.md 的文件，测试说明是 README_TEST.md 和 TEST_REFERENCE.md；这里分别对应“test.md”和“测试设置说明.md”。

原项目常用文档位置保留简短导航入口。根目录原始规格、任务书、工具约定及 D1 附件仍在原位置保留，保证工程引用可用。实际代码、日志和运行结果仍保存在项目中，说明文件夹应连同项目一起使用。

## 全部对应关系

| 想了解什么 | 新手版 | 原版 |
|---|---|---|
| 项目从哪里开始 | [README.md](新手版/README.md) | [README.md](原版/README.md) |
| 第一次运行测试 | [test.md](新手版/test.md) | [docs/README_TEST.md](原版/docs/README_TEST.md) |
| 需要时怎样调整测试 | [测试设置说明.md](新手版/测试设置说明.md) | [docs/TEST_REFERENCE.md](原版/docs/TEST_REFERENCE.md) |
| 各个代码文件做什么 | [代码阅读说明.md](新手版/代码阅读说明.md) | [docs/module_map.md](原版/docs/module_map.md) |
| 两个模块怎样连接 | [接口接线说明.md](新手版/接口接线说明.md) | [docs/cpu_control_interface.md](原版/docs/cpu_control_interface.md) |
| 什么时候等、什么时候继续 | [等待与跳转说明.md](新手版/等待与跳转说明.md) | [docs/hazard_forward_table.md](原版/docs/hazard_forward_table.md) |
| 数据必须什么时候到达 | [存储器时序说明.md](新手版/存储器时序说明.md) | [docs/memory_timing_contract.md](原版/docs/memory_timing_contract.md) |
| 收到对方代码后怎么做 | [真实模块接入清单.md](新手版/真实模块接入清单.md) | [docs/datapath_connection_checklist.md](原版/docs/datapath_connection_checklist.md) |
| 项目按回复改了什么 | [本次对接说明.md](新手版/本次对接说明.md) | [docs/control_reply_to_D1.md](原版/docs/control_reply_to_D1.md) |
| 对方接受了什么、保留了什么 | [对方回复说明.md](新手版/对方回复说明.md) | [docs/inputs/CPU-DP-IF-D1.md](原版/docs/inputs/CPU-DP-IF-D1.md) |
| 为什么补充这些接口 | [接口问题说明.md](新手版/接口问题说明.md) | [docs/interface_audit.md](原版/docs/interface_audit.md) |
| 各次改动及其原因 | [项目改动记录.md](新手版/项目改动记录.md) | [docs/interface_change_log.md](原版/docs/interface_change_log.md) |
| 已通过什么、未验证什么 | [测试结果说明.md](新手版/测试结果说明.md) | [docs/verification_report.md](原版/docs/verification_report.md) |
| 怎样查指令和预期输出 | [指令表阅读说明.md](新手版/指令表阅读说明.md) | [docs/decode_table.csv](原版/docs/decode_table.csv) |
| 你的硬件、逐模块 IO 和全部指令流程 | [硬件接口与完整指令说明.md](新手版/硬件接口与完整指令说明.md) | [Control 接口](../docs/cpu_control_interface.md) 与 [译码表](../docs/decode_table.csv) |
| 怎样核对结果对应的代码 | [验证记录文件说明.md](新手版/验证记录文件说明.md) | [docs/verification_manifest.json](原版/docs/verification_manifest.json) |
| 怎样确认图片来自哪次测试 | [波形来源说明.md](新手版/波形来源说明.md) | [docs/figures/provenance.json](原版/docs/figures/provenance.json) |
| CPU 与 CNN 怎样合作 | [整个系统说明.md](新手版/整个系统说明.md) | [face_recognition_soc_spec_v0.1.md](原版/face_recognition_soc_spec_v0.1.md) |
| 你的开发范围和交付内容 | [Control开发任务说明.md](新手版/Control开发任务说明.md) | [CPU_CONTROL_Codex_代码生成提示词.md](原版/CPU_CONTROL_Codex_代码生成提示词.md) |
| 什么时候需要管代理 | [联网说明.md](新手版/联网说明.md) | [network/README.md](原版/network/README.md) |
| 协作时遵守哪些约定 | [项目约定说明.md](新手版/项目约定说明.md) | [AGENTS.md](原版/AGENTS.md) |
| 按问题找文档 | [资料查阅说明.md](新手版/资料查阅说明.md) | [docs/README.md](原版/docs/README.md) |

## 关于数据表和图片

指令 CSV、验证 JSON、波形来源记录和 PNG/SVG 保留原内容，新手版配有独立的阅读说明。代码接口、测试数据和共享编码没有为了简化措辞而改动。

这里引用的最近一次硬件测试是 2026-09-14 的实际记录：30,463 项检查，零失败。本次只是整理说明，没有重新运行硬件仿真。[文档检查结果](文档检查结果.json) 单独记录链接、覆盖范围和文件保护检查。
