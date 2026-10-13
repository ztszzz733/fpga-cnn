# CV32E40X + Vicuna 2 独立小规模验证

> 2026-10-13 后续联合接入：原主 CPU、NVDLA 和 Vicuna 已在同一 SoC 中通过三项定向小测试，见 [联合接入说明](hybrid_soc_integration.md)。共享存储配置额外暴露了 FP32 指令顺序相关问题，当前测试程序采用已验证顺序；独立测试通过不等于任意集成程序可靠。

## 目的与边界

验证“CNN 内部小控制核 + 可编程向量单元”能否通过更换程序执行新算子。
本次使用官方配套的 CV32E40X 开发分支、Vicuna 2 和标量浮点子系统；
不修改现有 RV32I CPU、NVDLA、DATASRAM 或 SoC 顶层。
这不是完整 CNN 集成，不包含 UART、人脸模型或大图，也不是性能对比。

## 固定来源

- 官方测试工程：https://github.com/vproc/vicuna2_unit_testing
- 固定提交：`1574ca9c8bbebadb683a7142b5b5d3688bfff655`
- Vicuna 2：`6409dd155419c57959178a263e450a935f8d3cb7`
- CV32E40X：`e898ef54f3ea88aef6b1537db9b0102517da5984`
- 标量浮点子系统：`823a7fc1cca17ce4238cc460bdbb6a442bf9bec8`
- 各子模块许可证保留在原始源码中；交付时应按各组件分别核对许可。

## 仿真配置

- ISA：`rv32imf_zfh_zve32f_zvfh`；测试程序额外显式使用 `zicsr`。
- 向量寄存器 128 位、向量算术通路 64 位、存储接口 32 位。
- 两条流水线：`32:VLSU` 和 `64:VELEM,VALU,VMUL,VSLD,VDIV,VFPU`。
- Verilator 复用 NVDLA 工程工具，最大并发编译线程数为 2。
- 每次构建和每次仿真都有超时；每个程序另有 200000 周期执行上限。
- 向量寄存器长度不等于每周期运算数量；本配置不宣称达到某个加速比。

## 九项定向测试

1. INT32 残差相加。
2. INT32 逐元素乘法。
3. INT32 PReLU：负数除以 4，输入选为 4 的倍数，避免混入舍入差异。
4. FP32 加法。
5. FP32 乘法。
6. FP32 PReLU：系数 0.25，以整数符号比较、浮点乘法和掩码选择实现有限数域运算。
7. FP16 加法。
8. FP16 乘法。
9. INT32 点积：向量乘法、归约、跨批次累加。

每项处理 19 个元素，包含负数、零、正数，以及不足一个完整向量的尾部。
Python 独立计算预期值，对仿真 SRAM 写回的每个有效字节进行比对。
浮点用可精确表示的有限数，不覆盖 NaN、Inf、非规格化数、全部舍入模式或异常标志；
定向测试通过不能代替完整 ISA/浮点一致性验证。

## 如何运行

下载官方工程及固定子模块到 `third_party/vicuna2_tests`。原始源码保留不改。
`scripts/run_vicuna_small.py` 在 WSL 中复制到工程根目录旁 `.vicuna_build/source`，
仅改变仿真配置和给官方仿真驱动添加有界执行保护，构建缓存位于 `.vicuna_build/model`。

本机适配还包括：去掉 Verilator 5.038 不识别的 `IEEEMAYDEPRECATE` 警告选项，
并在模型生成后解析实际浮点子系统头文件名，替换官方 C++ 驱动写死的生成文件名。
LSU 独占一条流水线：这版多结果 LSU 与 VELEM 合并时，包装器没有对应端口组合。
以上均不修改 Vicuna、控制核或浮点算术电路的算法。

```text
python3 scripts/run_vicuna_small.py
python3 scripts/test_vicuna_small.py <本次 build/runs/..._vicuna_small 路径>
```

第二步要求预编译工具链及校验文件已保存到 `.tools/downloads`：
`xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz` 和 `.tar.gz.sha`。
脚本先比对官方 SHA-256，再解包到项目缓存，避免改变系统默认编译器。

运行记录保存在独立 `build/runs` 目录，状态含义：

- `PREPARED`：仅准备源码。
- `COMPILED_NOT_TESTED`：仿真器已编译，尚未验证程序结果。
- `PASS`：本次九项程序全部执行并逐字节校验通过。
- `PARTIAL_FAILURE`：至少一项测试失败，必须逐项查看，不等于全功能通过。
- `ERROR`：准备、编译或运行基础设施错误。

`wave.vcd` 是实际 RTL 仿真记录，可用 GTKWave 打开。官方驱动在一个时钟周期中
多次更新统计计数和 VCD 时间戳，其 `Total Cycles` 不能直接当作硬件时钟周期数；
硬件耗时应按波形时钟边沿或单独的周期计数核对。

## 集成之前还缺什么

主 CPU 的 MMIO 任务寄存器、内部程序加载与启动机制、共享 SRAM 仲裁、
任务完成/故障通知、NVDLA 与向量单元之间的数据格式及量化参数约定。
独立验证不会自动补齐以上系统接口，也不恢复已放弃的主 CPU IMEM 下载改造。

## 2026-10-13 实际结果与限制

`build/runs/20261013_204057_vicuna_small` 九项全部 PASS，逐字节比较实际 SRAM 转储。
复用模型 SHA-256：`732ed0113fb58a39f541bbccbef78fb3abdb5e48476672be54bfe4869a1ec916`。
本次重新编译硬件耗时 0；原模型编译 429.706 秒。
工具链改为 Windows 原生单次扫描，仅提取所需工具和共享库，39 秒完成。
执行入口：`scripts/resume_vicuna_tests.py build/runs/20261012_175753_vicuna_small`（WSL）。

首次诊断 `20261013_203617_vicuna_small` 的八项输出正确，但收尾 FENCE 卡住；
FP32 PReLU 使用 vmflt.vv 时超时。失败记录完整保留，不能算 PASS。
原因分别是默认封装 `fencei_flush_ack_i=0`，以及当前向量译码器缺少 vmflt.vv。
本次无缓存测试改用受向量写入互锁保护的标量读收尾；FP32 PReLU 改用符号位掩码，
浮点乘法仍由真实向量 FPU 执行。完整接入必须处理 FENCE 应答，软件须遵守实际指令子集。
正式结果、限制和 GTKWave 会话见 `deliverables/vicuna2_small/README.md`。
