# 用户主动暂停：重启前断点

2026-10-12，用户要求暂停并重启电脑。已停止本线程的工具链准备进程
（Windows Python PID 11844）；此前两个 WSL 准备进程也已中止。
不自动恢复、不自动编译，等待用户重启后明确继续。

## 已保留

- 官方源码及固定版本、工具链压缩包和官方 SHA-256 文件。
- 硬件模型已成功编译：`D:/code/FPGA1/.vicuna_build/model/verilated_model`。
- 成功编译记录：`build/runs/20261012_175753_vicuna_small/compile.log`，
  最后显示 `Built target verilated_model`；该次编译 429.706 秒、配置 14.014 秒。
- 复用记录：`build/runs/20261012_180952_vicuna_small/result.json`，
  已保存模型 SHA-256；其测试准备被中断，不能算 PASS。
- 九项小测试的程序生成器、独立参考结果、运行及交付脚本。

## 尚未完成

工具链解包仍未完成；部分文件已写入缓存，不能据此判断工具可用。
脚本仅在全部选定工具文件解包完成后写入 `ready.sha256`，中断状态不可冒充完成。
目前 **0 项 RTL 算子测试通过，尚无本轮有效仿真波形**。

## 恢复时

1. 先核对已编译模型与上述复用记录中的 SHA-256；无需重新下载源码或重编模型。
2. 完成工具链准备。此前 WSL 在 Windows 文件桥 `p9_client_rpc` 等待明显，
   单次流式解包仍慢；Windows 本地解包也由用户主动暂停，不能声称已解决。
   应优先减少跨系统大文件访问和重复解压，不重复启动并发准备进程。
3. 使用 `scripts/resume_vicuna_tests.py build/runs/20261012_175753_vicuna_small`
   创建新的独立测试目录，复用模型执行九项小测试。
4. 只有实际输出逐字节比对后才能给出 PASS；之后再执行
   `scripts/prepare_vicuna_results.py <本次新运行目录>` 生成正式结果和 GTKWave 会话。

暂停丢失的只是当前未完成的准备进程进度；已有下载和完成的模型编译不必重来。
没有修改生产 SoC CPU/NVDLA/DATASRAM，也没有运行大图仿真。
