# NEureka 适配说明

本次新增隔离入口 `rtl/neureka/face_soc_neureka_top.sv`，文件清单为 `rtl/filelists/system_neureka.f`。原 CNN 和原 SoC 入口保留。最大的六个模块仍是 CPU、CNN、DATASRAM、IMEM、CLOCK、IMAGE_BRIDGE。

## 数据路径

CPU 在 DATASRAM 中准备任务描述符，然后通过原来的 0x40000000 MMIO 接口提交队列。CNN 内部的控制器读取队列，调用真正的 PULP NEureka RTL、格式转换 DMA 或原来的后处理算子。计算结果通过原来的 11 客户端接口写回 DATASRAM。

NEureka 使用 HWC（一个像素的各通道相邻）排布。原 CNN 和后处理使用 CHW（一个通道的整张图相邻）排布。为了兼容原有程序，测试路径为：

`CHW 图像 → DMA 转 HWC → NEureka 卷积/量化 → DMA 转 CHW → 原 ReLU → 原 2×2 MaxPool → DATASRAM`

转换 DMA 在硬件中逐字节读写 SRAM，时间计入总耗时。权重按 NEureka 位平面格式离线打包；两版使用相同的逻辑权重。打包属于模型部署准备，不计入每次推理，两版都从已准备好的权重开始。

NEureka 的 288 位 HCI 请求由 CNN 内部 `neureka_banked_bridge` 转成最多九个 32 位客户端请求。四个 SRAM bank 仲裁这些请求，每个 bank 每周期至多一次访问。没有把 288 位接口误当成每周期都能完成的内存传输。桥接器维护每个字的请求和回复，合并后返回 HCI；非完整字写入拆成字节写，不覆盖旁边的数据。

特别注意：官方 streamer 的 `hci_core_r_id_filter` 明确要求 grant 后一拍返回。桥接器在 NEureka 保持 req 的期间先完成各 bank 的读写，等数据收齐才给 HCI grant，并在其下一拍给 r_valid。不能先立即 grant，再过若干拍返回；那会破坏内部响应归属。等待 grant 的时间计入实测周期。

## CPU 如何提交任务

MMIO 不变：写 `BASE+0x08` 设置描述符起点，写 `BASE+0x18` 设置任务数，写 `BASE+0x00 = 0x3d` 启动。读取 `BASE+0x04`：bit0 busy，bit1 done，bit2 error。写控制寄存器 bit1 可复位 CNN。

每个描述符仍占 32 字节，八个小端 32 位字依次为：`版本/op、IA、OA、WA、BA、H/W、CO/CI、LP`。版本为 1，即首字 `0x100 | op`。

| op | 功能 | 参数 |
|---|---|---|
| 11 | NEureka 卷积任务 | IA 指向 24 个官方配置寄存器字，其余描述符字段保留 |
| 12 | 图像排布转换 | IA/OA 为源/目的，H/W、CI 为张量尺寸；LP=0 为 CHW→HWC，LP=1 为 HWC→CHW |
| 2、3、6、7、8、10 | 原有后处理 | 原描述符格式，分别为带上限激活、残差加、ReLU、PReLU、池化、定点缩放 |

旧的 op0/op1/op9 描述符不能原样作为 NEureka 任务使用，新入口会报错。原入口仍支持它们。软件需要生成 NEureka 配置和打包权重，不能只把模块名字替换掉。

配置块的字 0～5 是权重、输入、输出、scale、逐通道 shift、bias 指针；字 6～14 是输入、输出、权重步长；字 15～19 是通道及空间分块数量和尾块长度；字 20～23 是 padding、权重偏移、filter mask、CONF0。测试生成器 `scripts/gen_neureka_benchmark.py` 给出了可运行的配置实例。

本版本开启预取时，CONF0[10] 和 [9] 同时置位，选择配套的内部权重 streamer；两个逻辑读取通道仍由官方内部互连汇入同一个 HCI 接口。每个卷积任务开始前，适配器执行官方 SOFT_CLEAR 命令并等待状态清理，再 acquire、配置和 trigger，避免前一任务的内部流状态影响下一任务。

新 SoC 入口的默认 SRAM 容量沿用旧值 256 KiB。大图 benchmark 显式设置为 4 MiB，实际接入相同任务时也必须相应设置 `SRAM_SIZE`，不能把大图地址表直接用于默认容量。

## 本次验证的范围

以实际测试报告为准。目标用例是 3×3、stride1、valid 卷积，8 位有正负值的权重、非负输入、32 位内部累加、右移量化到有符号 8 位，然后执行 ReLU 和 2×2/stride2 最大池化。测试使用真实 CPU 程序启动和轮询；独立 Python 整数运算核对卷积、ReLU、池化的每一个结果。

这份固定版本的 RTL 把 CONF0[26] 定义成 feature broadcast，而附带软件头文件把它标成 input signed，不能照抄该宏。基准图像统一归一化到 0～127，保证原有有符号输入 CNN 和此版本 NEureka 对同一字节的解释一致。负激活、其他卷积模式和完整人脸网络需要独立适配与验证。

当前适配队列按顺序执行任务，NEureka 内部启用输入预取；它不是旧版多算子乱序调度器的完整替代。当前 benchmark 的输入已经在 SRAM，UART 不进入计时。本次按最新要求停止大图测速，不提供加速比；已通过的小图结果不能用于推断串口输入整张图片到人脸识别完成的性能，也不代表已经恢复逐像素 UART 流式卷积。

入口参数 `ENABLE_OVERLAP` 仅为接口兼容而保留，在新队列中不控制调度或 NEureka 预取。预取由 op11 的 CONF0 配置决定。本次配置固定为开启。

## 仿真和资源的含义

两版采用同样的 100 MHz 仿真时钟和四 bank SRAM。周期数由 RTL 实测；毫秒由周期数/100 MHz 换算，不是电脑运行仿真花的墙钟时间。没有进行工艺综合，所以没有保证两版实际可达频率相同，也没有面积、功耗或单位面积吞吐的结论。NEureka 的硬件规模和原 8×8 阵列不同。

本地小图复现入口：Windows 下运行 `scripts/run_neureka_sim.ps1 -Size 11 -OutputChannels 3 -Repeats 2 -Cases neureka -Reuse 'build/runs/20261010_225915_neureka'`。脚本会在独立 `build/runs/*_neureka` 目录保存源文件哈希、程序、输入、参考值、仿真日志、任务事件和结果 JSON。已完成验证及其限制见 `deliverables/neureka_benchmark/适配与验证说明.md`。2026-10-11 的 256×256 RGB、8 输出通道大图卷积＋ReLU＋池化已验证通过，共核对 1,161,288 字节；波形与计时见 [大图控制波形说明](../deliverables/neureka_large_wave/波形阅读说明.md)。该用例从 SRAM 预加载，不包含 UART。

后续如需大图，可运行 `scripts/run_neureka_sim.ps1 -Size 256 -OutputChannels 8`。首次编译 NEureka 及大图 RTL 仿真可能需要较长时间；电脑运行时间不参与硬件性能比较。`--native-build` 可把编译临时文件放在 WSL 本地文件系统，结果和可复用仿真程序仍保存在工程内。`--reuse <上次通过的运行目录> --cases neureka` 可复用同一 SRAM 容量的程序，使用新图像重新做完整 RTL 仿真，结果记录保留原程序的源码哈希。修改 RTL 后应重新编译；需要原始逐拍波形时应使用启用 Waves 的新编译，不复用这里的无波形程序。

此 benchmark 配置生成器限制 CI/CO 在 1～32、图像边长 4～1024，属于本次适配范围，不代表 NEureka 硬件本身的上限。输入文件是已归一化的像素张量，不是 JPEG 压缩码流。权重打包、24 字配置和五个任务描述符均在 `gen_neureka_benchmark.py` 中生成。要放进完整 UART 流程，还需用现有加载协议传入这些数据，并让固件在加载成功后提交任务；本次计算侧程序直接使用仿真预置的 SRAM。

`scripts/lint_neureka.py` 检查六模块完整顶层的展开与连线；`scripts/run_neureka_bridge.py` 独立验证 SRAM 争用、部分字节写和 HCI grant 后一拍返回。架构图见 `deliverables/neureka_benchmark/neureka_architecture.drawio`，包含六模块总图和 CNN 内部图。
