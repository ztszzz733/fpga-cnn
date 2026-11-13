# 项目网络代理

- 用户所说的网络连接是 Codex 网络代理，不是虚拟机 SSH 或开发板。
- 已确认代理为 Clash Verge / Mihomo：`http://127.0.0.1:7897`。Windows 系统代理已经启用。
- 代理参数保存在 `network/proxy.psd1`；`.codex/config.toml` 为本项目的 Codex 命令环境设置相同的代理变量。
- 后续任务直接复用此配置。不要在每次对话开始时重新扫描端口、检查代理或重新配置系统网络；仅在实际网络请求失败或用户要求排查时诊断。
- 当前会话未加载新配置且确实需要联网命令时，在同一次 PowerShell 调用中先用 `Import-PowerShellDataFile .\network\proxy.psd1` 读取参数，再用 `[Environment]::SetEnvironmentVariable(..., ..., 'Process')` 设置代理后执行目标命令。环境变量不会从子进程反向传回已经运行的 Codex。
- 启动方式和适用范围见 `network/README.md`。更改代理地址时同步更新 `network/proxy.psd1` 和 `.codex/config.toml`。
- 不在项目中记录密码、令牌或私钥；不把代理参数持久化误称为保持跨对话连接，也不把 shell 代理配置描述为桌面客户端网络修复。

# CPU_CONTROL 工程约定

- 设计输入是根目录两份原始 Markdown 和用户在对话中提供的架构图；用户负责 CPU_CONTROL。原始文件保留，不擅自修改生产 Datapath/CNN。
- 已按 C1 实现并根据 CPU-DP-IF-D1 对齐；D1 原则接受 C1，公共地址/系统复位/真实存储时序仍待三方冻结。接口说明在 docs/cpu_control_interface.md，对齐记录在 docs/control_reply_to_D1.md，D1 原文归档于 docs/inputs/CPU-DP-IF-D1.md。实际 Datapath 未提供；只能报告 Control/stub 验证，不宣称真实 CPU/CNN 联调通过。
- 测试统一入口：`python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot`。本机实际可用工具为 Vivado XSim 2026.1，脚本已处理其启动环境；无需每次重新发现工具路径。
- 用户教程在 docs/README_TEST.md，实际结果与限制在 docs/verification_report.md。每次运行使用独立 build/runs 子目录，不能用旧 VCD/PNG 代替本次结果。
- Control 保持组合逻辑；所有跨级状态由 Datapath 持有。CNN Driver 是普通 MMIO 软件，不添加 STATUS/CONTROL 硬件端口。
