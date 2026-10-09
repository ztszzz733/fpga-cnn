# Codex 代理配置

本机代理：Clash Verge / Mihomo，`http://127.0.0.1:7897`。
Windows 系统代理已启用并指向该端口。使用时保持 Clash Verge 运行。

## 后续对话

本项目的 `.codex/config.toml` 为 Codex 执行的命令注入代理环境变量；项目必须受信任，且新启动的会话须加载该配置。`AGENTS.md` 要求直接复用这些参数，不要在每次对话时重新查找或测试代理。

这项配置作用于命令子进程，不能改变已经运行的桌面客户端自身的网络连接。Windows 系统代理本来就已持久化。仅写项目文件不能保证消除界面上的“重新连接”提示。

## 手动使用

在项目根目录运行。只需在需要时执行，不要每次对话都执行检查。

```powershell
# 当前 PowerShell 及它之后启动的程序使用代理（无需更改脚本执行策略）
$proxy = Import-PowerShellDataFile .\network\proxy.psd1
foreach ($name in $proxy.Keys) {
    [Environment]::SetEnvironmentVariable($name, $proxy[$name], 'Process')
}

# 可选：检查代理到 OpenAI API 的 HTTPS 通路
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\network\proxy.ps1 -Mode Check

# 从项目目录启动 Codex CLI，并让它继承代理变量
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\network\proxy.ps1 -Mode Cli

# 完全退出 Codex 桌面应用后，以代理变量启动桌面应用
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\network\proxy.ps1 -Mode Desktop
```

本机默认禁止 PowerShell 脚本，上述 `-ExecutionPolicy Bypass` 只作用于此次启动的 PowerShell，不更改系统或用户执行策略。

桌面启动入口仅负责传递环境变量，不保证应用的所有网络组件都采用这些变量；系统代理仍维持原有配置。脚本不会关闭当前应用，也不修改用户级环境变量或系统代理。已经运行的应用不会继承另一个进程后来设置的环境变量。

## 验证记录与排查范围

2026-09-13：本机 7897 端口由 `verge-mihomo.exe` 监听；显式使用该代理访问 `https://api.openai.com/v1/models` 返回 HTTP 401（未发送凭据，证明该次 HTTPS 通路可用）。访问 ChatGPT 首页返回 HTTP 403，不能据此判定登录会话或模型长连接正常。

尚未验证重新启动后的桌面应用是否仍显示“重新连接”。若提示持续出现，需要结合发生时间和客户端错误日志排查，不能直接归因于代理参数未保存。

更换端口时同步修改 `proxy.psd1` 和 `../.codex/config.toml`。代理账号、密码或令牌不要写入这些文件。

参考：[Codex 项目配置](https://learn.chatgpt.com/docs/config-file/config-basic)、[命令环境配置](https://learn.chatgpt.com/docs/config-file/config-reference)。
