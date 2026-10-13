# NVDLA＋Vicuna 2 真实 SoC 小测试

**本轮 3/3 PASS。** 来源：`build/runs/20261013_211215_hybrid_soc`。
原 RV32I CPU 实际运行固件，配置 NVDLA、装入并启动 Vicuna 程序；两套真实 RTL 通过共享 DATASRAM 交换数据。
顶层仍为六大模块，CNN 内包含 NVDLA 和 CV32E40X＋Vicuna 2。

| 用例 | 结果 | 电脑仿真耗时/秒 | 100 MHz 假设下硬件时间/μs | Vicuna 任务数 |
|---|---|---:|---:|---:|
| tiny_chain | PASS | 5.387 | 156.05 | 2 |
| conv_chain | PASS | 37.347 | 841.79 | 2 |
| pool_parallel | PASS | 8.645 | 307.13 | 3 |

本轮三个仿真进程合计 **51.378 秒**。本轮复用模型，编译为 0.00 秒。
首次联合模型编译 173.73 秒，另有展开检查；不包括固件编译、排错和文档生成。
硬件时间包含 CPU 程序装载、配置、轮询与计算，不能当作单算子耗时，也不代表上板频率已经验证。

## 做了什么

- `tiny_chain`：NVDLA 最小卷积 → SRAM → Vicuna INT8 PReLU，检查部分字节写入和再次启动。
- `conv_chain`：NVDLA 6×8、192 输入通道、32 输出通道的 3×3 卷积＋SDP → SRAM → Vicuna INT8 PReLU。
- `pool_parallel`：NVDLA 8×8×64 的 2×2 池化，与 Vicuna 的 256 元素 FP32 PReLU 并发；之后串联处理池化写回区并重复启动。

NVDLA 三项输出各自匹配官方 CRC32；Vicuna 输出逐字节比对，末尾保护字节保持不变。
并发场景统计见 `pool_parallel/metrics.json`：`both_request_cycles` 是双方同周期发存储请求的周期数，`vector_stall_cycles` 是 Vicuna 被仲裁暂缓的周期数。它们不是 PE 利用率或加速比。

**输入采用 SRAM 预加载，UART 本轮保持空闲；没有运行大图或完整人脸识别网络。**

## 需要明确的限制

集成配置下发现 FP32 PReLU 的“先比较、后乘法”指令顺序存在结果错误；本轮改为等价的“先乘法、后比较、再选择”并重新验证。根因尚未彻底定位，不能据此宣称任意向量程序都正确。
失败记录保留在 `build/runs/20261013_210250_hybrid_soc`，软件顺序诊断见 `build/runs/20261013_211032_hybrid_fp32_diagnostic`。
这与此前独立九项小测试的范围不同；新的共享存储时序暴露了额外限制。

## 看波形

双击各目录 `open_wave.cmd`。会话共 39 根不重复控制/数据观察信号，按 CPU、配置、NVDLA、Vicuna、共享内存排列并配色。
每项有 `overview.png` 全程图和 `first_vector_write.png` 首次串联写回放大图，均来自本轮真实 VCD。
`completion.png` 放大最终完成；`pool_parallel/concurrent_memory.png` 显示两套引擎同时请求 SRAM。
横轴为 ns，按 100 MHz 时钟实际推进模拟时间，同时保留官方 RAM 延迟。

| 信号 | 来源 → 去向 / 作用 |
|---|---|
| cpu_pc | 主 IMEM 取指地址，证明 CPU 在执行程序 |
| mmio_addr/wdata/re/we | 主 CPU → CNN 零等待命令寄存器 |
| mmio_rdata/ready | CNN → 主 CPU；ready 恒为 1，目标执行完成要看 cmd_done/软件 STATUS |
| cmd_busy/done/error | CNN 内部配置命令事务的状态；与算子任务完成不同 |
| config_state | NVDLA CSB 配置适配器状态 |
| nv_irq | NVDLA → CNN：未屏蔽任务完成标志，CPU 软件轮询原生完成状态 |
| read_state/write_state/read_beats/write_beats | NVDLA 存储桥状态及累计传输拍数 |
| vec_busy/done/jobs/code | Vicuna 任务活动、完成、累计任务数和结果码；busy 不等于每周期都运算 |
| vec_pending | 向量寄存器待写位图，不是 PE 忙闲位图 |
| vec_state | Vicuna 存储桥：0 空闲、1 请求 SRAM、2 等应答、3 返回内部核 |
| cnn_valid/ready/response/write | CNN ↔ SRAM，bit0=NVDLA 读，bit1=NVDLA 写，bit2=Vicuna |
| vec_addr/wdata/rdata | Vicuna 存储桥 ↔ DATASRAM：实际数据地址/写数据/返回数据 |
| vec_reads/writes/stalls | Vicuna 桥已完成 SRAM 读/写次数与等待仲裁周期数 |
| fault | CNN 故障状态，正常测试保持 0 |
| phase/status | CPU 写 SRAM 的测试观察字，非新增板级端口；phase=1 装程序、2 配置、3 等 NVDLA、4 等并发 Vicuna、5 串联、6 再次启动、7 结束 |
| uart_tx/load_req | UART 输出和 CPU 装载请求，本轮均无传输 |

当 `cnn_valid[2] && cnn_ready[2] && cnn_write[2]` 为 1 时，SRAM 接受 Vicuna 写回；随后 `cnn_response[2]` 为 1 表示完成。
串联输出从 0x18000 起，再次启动输出从 0x1A000 起；并发 FP32 输出在 0x31000。
软件任务选择及寄存器说明见 [接口文档](../../docs/hybrid_soc_integration.md)，结构图为 [可编辑 draw.io 文件](architecture.drawio)。

接口短回归 PASS，见 `adapter_checks/result.json`。已实际用 GTKWave 加载三份会话，各显示 39 个信号；日志位于每个用例目录。

并发放大图中约 64.105 μs，`cnn_valid=5`（二进制 101）表示 NVDLA 读与 Vicuna 同时请求；`cnn_ready=4` 表示该周期先接受 Vicuna，下一周期再接受 NVDLA。不要只看请求数量推断同周期完成数量。
