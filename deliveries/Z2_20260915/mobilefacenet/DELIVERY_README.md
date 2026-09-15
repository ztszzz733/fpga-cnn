# CPU 联调交付包 Z2

日期：2026-09-15。仅包含新版 mobilefacenet；无旧版 RTL、工具安装包或本机 .deps。

正式回复：docs/发给CPU负责人_Z方对DZ1的正式回复_Z2.md。
容量报告：docs/DZ1_memory_audit.json。

从本目录的父目录运行：

```text
python mobilefacenet/scripts/run_tests.py accelerator_regs accelerator_mem_if top_smoke
python mobilefacenet/scripts/run_tests.py mobilefacenet --tasks mobilefacenet/build/vectors/tasks.txt
python mobilefacenet/scripts/run_tests.py mobilefacenet --tasks mobilefacenet/build/onnx_fixture/export/tasks.txt
```

Python 与 Icarus Verilog/VVP 必须可用；可通过 --iverilog / --vvp 指定路径。
以上命令使用内置测试或预生成向量。重新生成向量、执行软件参考或导出 ONNX 时，
需另安装 requirements.txt 中的依赖，再按 README 运行 verify_all.py。

rtl/files.f 内的路径以 mobilefacenet 目录为基准；集成时不要同时加入旧版 RTL。
ONNX tasks.txt 的数据路径已经改为工程内相对路径，寄存器值与向量字节未改变。
模型 metadata 保留历史来源路径用于追溯，运行预生成任务不依赖原机器路径。

build/verification.json 和 docs/verification.md 是此前完整验证记录。
build/Z2_delivery_checks.json 是本次在交付副本上执行的有限复核，不能代替完整系统验证。
DELIVERY_MANIFEST.json 记录除自身之外各文件的 SHA-256；压缩包旁提供包体 SHA-256。
本包未包含实体双口 SRAM wrapper、B 口适配器、官方 stub 或真实训练人脸模型。
