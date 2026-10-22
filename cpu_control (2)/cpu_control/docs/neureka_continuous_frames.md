# Neureka 六模块连续帧调度

本次修改面向 `face_soc_neureka_pipeline_top`：CNN 处理当前帧时，图像桥加载下一帧，CPU 执行输入统计、消费已完成结果或准备空闲槽的任务。六模块端口、模块间信号及板外七根信号保持不变；CPU Control/Datapath、IMEM、四 bank SRAM、Neureka/Vicuna 计算 RTL 及原有分块双缓冲不改。

## 图像桥描述符

`image_bridge_autoload` 新增默认关闭的编译参数 `DESCRIPTOR_MODE`。旧入口仍使用固定参数批次；Neureka 流水入口启用描述符模式，通过已有 SRAM 读接口获取参数，再以原 IMIO/IMOR UART 协议读取外部数据。CPU 的三线 `load_req/load_complete/load_error` 不变，没有图像桥到 CNN 的新直连。

在这个入口中，顶层的 `SOURCE_BASE/LOAD_BASE/LOAD_BYTES/EXPECTED_CRC32` 不再决定运行时传输；旧入口保持其原意义。描述符位于 `SRAM_BASE+0x60`，共五个小端 32 位字：

| 偏移 | 内容 |
|---|---|
| +0x00 | magic/version：`0x31444c49` |
| +0x04 | 外部数据源字节地址 |
| +0x08 | SRAM 目标字节地址，可非字对齐 |
| +0x0c | 非零字节数 |
| +0x10 | 整帧 CRC32，算法与原批次 CRC 相同 |

CPU 在握手完全空闲时填写参数，最后发布 magic，执行 fence 后拉起请求；请求至完成确认期间不得改描述符。桥每次复制参数到内部寄存器；SRAM 读授权、返回分别处理，只有一个读在途。

硬件检查 SRAM 范围、源地址溢出、控制寄存器覆盖和描述符自身覆盖。全部错误保持“完成附带错误 → CPU 确认 → 锁定直至复位”，避免迟到数据被下一任务接收。新增内部错误码：10 描述符地址非法，11 描述符请求/返回超时，12 描述符内存错误，13 magic 错误；加载区域错误仍为 1。

## 缓冲区和驱动

```text
输入帧 A/B → Neureka → 中间 tile A/B → Vicuna → 输出帧 A/B
    ↑                                            ↓
图像桥加载空闲输入                           CPU 消费完成结果
```

输入帧 A/B 与原有中间 tile A/B 是不同区域。`sw/neureka_pipeline/cnn_frames.h` 管理两个帧槽：各有输入、输出、tile 描述符和原生配置，复用中间 tile 缓冲及只读权重。

状态为 `FREE → QUEUED → LOADING → READY → RUNNING → RESULT → FREE`。

- `cnn_frames_init`：硬件空闲时登记布局，检查输入、输出、描述符、配置、中间缓冲、控制区和调用方保护区域互不重叠；检查每个 tile 的配置指针、输出范围和输入起点。
- `cnn_frame_submit`：只允许提交 FREE 槽，设置外部源及 CRC；按提交顺序运行 CNN。
- `cnn_frames_poll`：执行一次协作式调度后返回，沿用原邮箱的有界事务等待，不整批等待 CNN；CPU 可在调用间做其他工作。
- `cnn_frame_release`：结果消费完后显式释放 RESULT 槽；加载、计算或未消费的槽不能被重新提交。

加载和 CNN 可分别在途。下一帧未完整接收并通过 CRC 时不会提交给 CNN。错误冻结队列及缓冲区所有权；应用超时不能自行回收在途存储，需要停止使用并系统复位。

这是合作式软件所有权管理，不是全 SRAM 硬件访问保护。其他 CPU 代码不得绕过驱动写活跃数据或程序。原生配置的全部输入/权重/尺度及 stride 足迹仍由调用方保证，驱动只检查输入起点，不能推导任意原生配置的完整访问范围。权重、尺度、程序源、栈和应用数据须通过 protected_regions 登记；布局改变须在队列空闲时重新验证。更改 SRAM/控制地址时，驱动宏 `CNN_SRAM_BASE/SIZE`、`CNN_LOAD_CONTROL/DESCRIPTOR` 必须匹配硬件。

## 连续四帧示例

`firmware/neureka_frames_demo/main.c` 是真实主 CPU 执行的 RV32I C 固件。启动汇编只设置 SRAM 栈，链接脚本禁止把运行时常量放进不可经数据口读取的 IMEM。

| SRAM 区域 | 用途 |
|---|---|
| 0x40 / 0x44 | CPU 本地加载控制/状态，不是实际 RAM |
| 0x60–0x73 | 图像桥描述符 |
| 0x80–0x93 | 完成、提交数、消费数、CPU 工作字节数、错误详情 |
| 0x100 / 0x200 | 两组各四个 tile 描述符 |
| 0x1000 / 0x1200 | 两组原生配置，各 384 字节 |
| 0x2000 / 0x3000 | 输入 A/B，各 405 字节 |
| 0x4000 / 0x4800 | 共享权重/尺度 |
| 0x5000 | 四帧源地址、CRC、输入统计和输出校验值 |
| 0x10000 / 0x11000 | 原有中间双缓冲，各 1 KiB |
| 0x12000 / 0x13000 | 输出 A/B，各 455 字节 |
| 0x20000–0x23fff | 向量程序源保留区 |
| 0x38000–0x3ffff | CPU 栈保留区 |

UART 接收四个不同的 15×9×3 输入，各 405 字节，每包 63 字节、尾包 27 字节。每帧四个 tile 做 3×3 卷积和 INT8 PReLU，输出 455 字节。CPU 在 CNN 工作时计算输入统计，条件允许时消费上一帧结果，再释放结果槽。权重、配置、程序源及期望值由 SRAM 初始化提供；这还不是仅提供外部图像即可部署任意模型的上板固件，外部设备也须实现原 IMIO/IMOR 协议。

```text
python scripts/run_neureka_frames.py
python scripts/run_neureka_frames.py --real-cores
python scripts/run_autoload_integration.py
python scripts/run_neureka_pipeline_control.py
```

默认使用本机 Vivado 的 RV32I GCC。其他环境设置 `RISCV_GCC` 指向交叉编译器，同目录须有 objcopy/objdump。CPU 机器码、初始 SRAM、四帧数据、独立 oracle 和日志保存在独立 `build/runs/*_neureka_frames`，不替换旧演示固件。

默认测试使用 **仅限测试的标量卷积/PReLU 行为模型**；主 CPU、UART 桥、SRAM、命令邮箱、tile 调度器和六模块顶层为生产 RTL。模型通过实际 SRAM 请求测试竞争和数据所有权，有额外延迟/无额外延迟分别模拟收图快于/慢于计算。模型不进入生产 filelist。`--real-cores` 使用固定版本真实核，不自动回退到模型。

## 验证状态

2026-10-22，`build/runs/20261022_165909_947172_neureka_frames/result.json`：默认回归 PASS。

- 两种时序均完成四帧，共 1820 字节结果逐字节匹配独立 oracle，输入 A/B 复用，输出边界完好。
- CPU 输入统计、结果校验、重复提交/提前释放拒绝和布局重叠检查通过。
- 下一帧整帧 CRC 错误时，不启动该帧 CNN，保留在途存储所有权。
- 描述符 magic、零长度、控制区/自身覆盖、SRAM 越界、源地址溢出、请求/返回超时、内存错误、完成保持和复位恢复通过。
- 两种成功时序均观察到 CPU、CNN、图像桥同周期被 SRAM 接受请求，证明控制和仲裁并发，不代表真实核性能。

原固定批次自动加载六项回归及原 tile 调度器回归也通过，分别见 `20261022_165933_472426_autoload_integration` 和 `20261022_165933_neureka_pipeline_control`。

真实核也在本地源码副本运行过 `--real-cores`，结果保存在 `fpga-cnn-moon/cpu_control (2)/cpu_control/build/runs/20261022_170414_959878_neureka_frames/`：真实 Neureka、Vicuna、主 CPU、桥、SRAM 和本次连续帧测试台编译、静态展开及模型生成成功，仿真 FAIL。在 0 ps 的 `cv32e40x_alignment_buffer.sv:115` 再次出现 XSim kernel exceptional condition，未执行到任何一帧计算；日志 `frames_0.log` 和 `result.json` 保留失败，不回退为模型通过。

因此真实 Neureka/Vicuna 连续帧数值、指定 FPGA 综合/时序及上板仍待验收。不得把行为模型周期数作为真实 CNN 加速比。
