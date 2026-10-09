# Datapath 隔离合并区说明

本目录用于接收、适配和回传 Datapath 负责人的代码，避免覆盖 CPU Control 工程中的正式 RTL。

## 目录用途

| 目录 | 用途 | 是否允许修改 |
|---|---|---|
| `upstream_20260917/` | 从负责人 ZIP 原样解压的只读基线，共 43 个文件 | 否 |
| `delivery/` | 可交付副本；保留原 43 个文件并加入本项目 B1 存储子系统 | 仅在这里修改 |

输入包：`D:\QQ\face_recognition_soc_datapath_complete.zip`  
输入包 SHA-256：`7DCAD4FB247B2B12A172009B63FD2F8C5506DBD57F4107793C95A4EB77ECD91C`

当前适配没有改动负责人原来的 43 个文件。新增代码位于：

- `delivery/rtl/soc_memory/`
- `delivery/rtl/filelists/datapath_b1.f`
- `delivery/tb/unit/tb_b1_memory_subsystem.sv`
- `delivery/docs/project_B1_integration_report_20260929.md`

## 验证命令

```powershell
python scripts\run_partner_datapath_b1_tests.py
python scripts\run_real_datapath_review.py --datapath-root partners\datapath\delivery
```

## 打包回传

在工程根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_datapath_delivery.ps1
```

脚本先逐文件核对原 43 个文件与只读基线完全相同，再生成带 SHA-256 清单的 ZIP。输出位于 `build/deliveries/`，不会覆盖旧回传包。
