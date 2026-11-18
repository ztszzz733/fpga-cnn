# FPGA CNN / EES331

`moon` 分支最新合并工程：**[ees331_swplan_bank2](ees331_swplan_bank2/README.md)**（2026-11-19）。

- 共享缓存：两 bank，每 bank 196 KiB，总容量 392 KiB。
- 算子：两个 3×3、四个 PW8 1×1、两个 Post、Add、Pad；DW7 沿用关闭配置。
- ARM FreeRTOS 软件调度和 K3 软件规划读段已接入，板级顶层源码保持原受测版本。
- 缓存、读段、K3 参考测试及两张 112×112×3 图片的真实 RTL 联合仿真已通过；PS/DDR 使用模型，ARM 调度公共 C 代码在原生环境执行。
- 100 MHz 为目标；本版本尚未综合、布局布线或上板，不能据此认定时序通过。

入口：

| 内容 | 文件 |
|---|---|
| 工程说明、配置及复现命令 | [README](ees331_swplan_bank2/README.md) |
| 验证结果与限制 | [验证结果](ees331_swplan_bank2/验证结果.md) |
| 顶层连线图与预览 | [图表说明](ees331_swplan_bank2/docs/diagrams/README.md) |
| RTL 编译清单 | [system_ees331_reduced.f](ees331_swplan_bank2/source/rtl/filelists/system_ees331_reduced.f) |
| ARM 调度源码 | [arm_schedule](ees331_swplan_bank2/arm_schedule) |
| 回归及源码核验记录 | [verification.json](ees331_swplan_bank2/verification.json) |

分支中原有的 `cpu_control (2)/cpu_control`、`releases` 和 [更新说明](更新说明.md) 保留为历史资料。本次工程位于独立目录，请使用该目录的源码、ROM 和 filelist，避免混用旧版文件。
