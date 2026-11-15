# P1 对齐接口审计

2026-09-28更新：生产Control已按[B1审计](control_B1_alignment_review_20260928.md)复核，与70位请求、35位返回的B口仲裁方案无功能冲突，不修改C1或生产RTL。用户已给出B1开发参数；D/Z回签、实体wrapper、仲裁器和真实CNN验收仍待完成。

2026-09-17更新：已收到生产Datapath，并完成真实Control+生产Datapath的ADD和混合程序有限联调。下文“尚未收到生产顶层”保留为2026-09-14历史状态，不再代表当前事实。

2026-09-14：M / Control 已正式接受 C1 作为 v1.0 开发基线，D1 12 项均有本方回复。对照 P1，生产 RTL 已具备所需控制功能，本次未改端口、编码和流水级，不增加跨级状态或 CNN 直连端口。

- [正式确认、生产清单、差异表与 S-01～S-10](control_reply_to_P1.md)
- [D1 逐项回复](control_reply_to_D1.md)
- [48 端口完整契约](cpu_control_interface.md)
- [联调序列与期望控制信号](control_datapath_directed_tests.md)
- [实际回归证据](verification_report.md)

2026-09-14当时：Datapath M1 PASS仅为P1的对方进度报告；当时尚未收到其package、生产顶层和真实存储wrapper。后续接入结果以上述2026-09-17更新和[对接核查](datapath_connection_review_20260917.md)为准。

历史设计问题的来龙去脉保留在 [归档审计](../说明文档/原版/docs/interface_audit.md)，其中旧的候选状态由本次正式回复更新。
