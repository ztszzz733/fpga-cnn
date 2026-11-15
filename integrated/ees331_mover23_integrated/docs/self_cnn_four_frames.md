# CNN 固定流程：按图片地址自主调度四图

本轮实现用户确认的方向：配置一份固定网络流程，向 CNN 提交图片地址；CNN 自己展开各图片的任务，在满足层间依赖和缓冲区生命周期的前提下，把就绪任务分配给空闲算子。主机不逐层启动算子，也不指定图片绑定哪套卷积。

入口为 `rtl/cnn_stream/self_fixed_network_top.sv`，编译清单为 `rtl/filelists/cnn_self_stream.f`。原双图入口和旧 SoC 入口保留。本轮 SRAM 为 `bai-datasram` 分支 `0f7cc8d35e21e5e6458da15797512e9e6a4eddbd` 的原样源码，来源和 SHA256 见 `rtl/cnn_stream/bai/SOURCE.json`。

## 范围与固定流程

先验证 4 张不同的 7×7 RGB 图和诊断权重，每图固定 11 步：

`Pad → Conv3 → Post/ReLU → Pad → DW3 → Post/Clip → Conv1 → Post → Add → DW7 → Post`

Add 的另一个输入来自第一层 Conv3 的量化输出，因此保留真实残差跨层生命周期。所有算术均由 RTL 执行，软件参考只用于比较。每图最终 8 字节，不是完整 MobileFaceNet 的 128 维 embedding。

这是跨图片、跨算子阶段的流水：一张图完成某层后，下一层可以使用另一类算子；释放的卷积单元立即可服务其他图片。当前同一图内的上述主链顺序执行，没有实现卷积层内逐行直通，也没有宣称调度达到理论最优。

## 外部接入顺序

1. 全局复位；通过现有 CPU A 口或 IO 口准备共享权重、量化参数。图像也可预先写好。
2. `configuration_ready=1` 时，通过 `template_valid` 写入一份流程，`template_index` 必须从 0 连续递增。当前默认最多 16 步，最多 64 个展开任务。
3. 通过 `address_valid` 提交 1～4 个地址描述：`address_slot` 从 0 开始、`image_base`、`workspace_base`、`address_frame`。每图拥有四个工作槽；各工作区互不重叠，且不能覆盖输入、权重、参数。工作区地址需要 4 字节对齐。
4. 设置 `image_count` 和 `unit_enable`，脉冲 `start`。CNN 内部将模板展开成每图命令、前驱编号、消费者掩码、槽 owner 和结果描述，然后自动运行。
5. 每图内容确实写完后，提交 `frame_valid / frame_slot / frame_id` 并保持至 `frame_ready` 握手。`frame_id` 必须匹配该 slot 的 `address_frame`。预存图片可连续提交全部就绪标记；逐张输入时，写完一张即提交一张，继续写下一张。只有已提交图片的任务允许读取 SRAM。
6. `result_valid` 提供 `result_frame / result_addr / result_bytes`；外部通过 SRAM IO 口读完结果并收到最后一个读响应后，才能置 `result_ready`。此握手释放结果槽。`compute_done` 仅表示计算完成；`done` 还要求所有结果已取走、所有槽已释放。

计算阶段不再需要主机逐层控制。当前为有限批次原型；下一批需要 `clear` 并重新配置。无无限流式队列、CPU 固件/MMIO 寄存器包装或 UART 协议改造。

## 模板地址与依赖

模板使用原 16×32 位命令格式，算子参数见 `docs/self_cnn_interface.md`。本入口由硬件覆盖 word13=帧号、word14=帧 slot。

| 模板字段 | 含义 |
|---|---|
| `template_source_modes[1:0]` | word1 来源：0=共享绝对地址，1=图片基址+偏移，2=工作区基址+偏移 |
| `template_source_modes[3:2]` | word2 来源，编码相同；卷积权重通常为 0，Add 第二输入为 2 |
| word3 | 当前图工作区内的目标偏移；由硬件加 `workspace_base` |
| word4 | 共享量化参数绝对地址 |
| `template_dep_valid/dep0/dep1` | 单图模板内的前驱，必须小于本步骤编号 |
| `template_allocate_slot` | 单图内 0～3 号槽 |
| `template_hold_mask` | 本张图中所有读取该输出的步骤及生产者；不能遗漏残差读者 |
| `template_use_valid/use_slots/use_owners` | 最多三个源槽以及产生该版本的单图步骤编号 |
| `template_result_valid/result_bytes` | 标识最终可交付输出及字节数 |

展开的节点编号为 `step * image_count + frame_slot`。槽编号为 `4 * frame_slot + local_slot`。模板的前驱、消费者和 owner 全部在硬件内按此规则转换。软件生成的 `commands.hex/metadata.hex` 在测试中只作为独立预期值，绝不驱动 CNN 配置口。

模板内容与物理地址布局由离线网络导出工具保证一致。当前控制器拒绝非连续模板、非法 opcode/源模式/前驱、重复地址 slot、未对齐工作区、零图片数及缺失地址；不会自动证明所有地址区间和消费者声明正确。不要把不完整模板当成可安全执行的网络。

## 算子池与存储接口

默认候选配置：K3×4、K1×2、DW7×1、Post×1、Add×1、Pad×1，共 10 个算子客户端。K3 普通卷积和 DW3 共用池。K3/K1/Post 的数量均可参数化；`unit_enable` 在运行开始锁存，每类必须至少启用一套。

算子编号依次为 K3 池、K1 池、DW7、Post 池、Add、Pad。调度器扫描就绪节点，每类池轮转分配，不把某张图固定绑在某个算子上。`operator_work` 对卷积表示真实 MAC，对 Post/Add/Pad 表示 SRAM 接受输出写入；`operator_busy` 包含访存等待，两者不能混用。

SRAM 为 256 KiB、四个真双口 bank，bank=`(byte_addr>>2)&3`。CPU A 口固定一拍；CNN 多客户端和图像 IO 共同竞争各 bank 的 B 口。不同 bank 可并行，同 bank 轮转，同字 CPU 访问优先、B 口等待。图像数据真的通过 IO 请求写入，不是 TB 偷填结果或独立零延迟内存。

CNN 读写均等待 `mem_response`；IO 读等待 `io_mem_rvalid`，**IO 写在 `req && gnt` 时完成，不会再返回写 rvalid**。尾部不足四字节由 `io_mem_be` 控制。SRAM 的 `cnn_mem_fault` 锁存到全局复位，单独 `clear` 不能清除此错误。`clear`/故障取消时，外部同时停止旧图像请求、丢弃旧结果确认；IO 口并不受 SRAM 内部 `cnn_cancel` 自动取消。

## 验证和复现

```powershell
D:\python\python.exe scripts/test_stream_programmer.py
D:\python\python.exe scripts/run_self_stream.py --sweep
D:\python\python.exe scripts/run_self_stream.py --configs four_k1 --modes overlap serial cpu_collision_slow_reader clear_restart memory_fault_restart disable_k3_0 preloaded
```

`--sweep` 只编译一次最大算子池，通过禁用实例比较活跃资源数量，避免把不同编译版本当成同样条件。候选配置还会单独编译为实际 10 实例并做回归。每次均保存源/数据哈希、周期计数、每个算子的工作/等待统计、输入与计算事件。可使用 `--images a.png b.png c.png d.png` 替换四张诊断输入，测试仍缩放为 7×7。

结果与图示见 `deliverables/self_cnn_four_frames/README.md`。最终报告只引用其中列出的已通过运行；之前空 VCD 的调试运行不作为波形证据。

当前重点是并行与流水控制。完整 MobileFaceNet 仍需要完整网络模板导出、更多任务/缓冲区容量规划及全网数值回归。原 Post/DW7 的 RAM 推断问题尚未修复，之前完整综合失败仍然适用；本轮不宣称新增池已满足板级资源或时序。100 MHz 只用于仿真时钟，不是实现频率承诺。
