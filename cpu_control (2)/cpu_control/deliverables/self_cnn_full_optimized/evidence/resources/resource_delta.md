# 卷积实例数量调整：既有综合资源证据复核

本次只读取既有报告并计算，没有重新综合、没有新增仿真，也没有修改 RTL。
候选由 **K3×4、K1×2** 改为 **K3×2、K1×4**；DW7、Post、Add、Pad 各一套，总实例数仍为 10。

## 单核证据

| 单核 | LUT | FF | RAMB36E1 | RAMB18E1 | BRAM36 等效 | DSP48E1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| K3 | 1,938 | 1,505 | 6 | 0 | 6 | 0 |
| K1 | 1,951 | 1,491 | 2 | 1 | 2.5 | 0 |

两份报告均为 Vivado 2026.1、`xc7z020clg484-1`、独立 OOC 综合，参数 `MAX_CHANNELS=512`、`TILE=2`，分别设置 `MAX_KERNEL=3/1`。
时钟约束为 **10 ns（100 MHz）**，综合后最差 setup slack 均 **+0.078 ns**，没有布局布线。报告的输入/输出边界还存在未约束路径，不能据此宣称整个 CNN 通过 100 MHz 时序。

当前 `self_conv_engine.sv` SHA256 与两次综合记录完全一致：
`5bbe644bb8398c4e159588ff690d1317734978bcfa410cc923625e9cdabf181b`。
当前集成代码对每个核使用相同的 `MAX_CHANNELS=512`、`TILE=2`，K3/K1 分别选 `MAX_KERNEL=3/1`。

## 六个卷积核的算术估计

| 项目 | 原 K3×4 + K1×2 | 候选 K3×2 + K1×4 | 候选减原配置 |
| --- | ---: | ---: | ---: |
| LUT | 11,654 | 11,680 | **+26** |
| FF | 9,002 | 8,974 | **−28** |
| RAMB36E1 | 28 | 20 | −8 |
| RAMB18E1 | 2 | 4 | +2 |
| BRAM36 等效块 | 29 | 22 | **−7（−24.14%）** |
| DSP48E1 | 0 | 0 | 0 |

以该器件 53,200 LUT 为分母，卷积部分约从 **21.91%** 变为 **21.95%**。这只是六个卷积核相加，不是整个 CNN 的 LUT 占用。
以 140 个 BRAM36 等效块为分母，该卷积池约从 20.71% 变为 15.71%。相加结果尚未包含集成优化或布局影响。

## 局部缓存确实减少

源码声明：`EDGE=2*(TILE-1)+MAX_KERNEL`，输入缓存 `EDGE²×MAX_CHANNELS` 字节，权重缓存 `MAX_KERNEL²×MAX_CHANNELS` 字节。
这些尺寸覆盖步幅 2 的窗口，不能只按步幅 1 的 2×2 tile 加 halo 计算。

| 声明的局部存储 | 单 K3 | 单 K1 | 原六核合计 | 候选六核合计 |
| --- | ---: | ---: | ---: | ---: |
| 输入缓存 | 12,800 B | 4,608 B | 59 KiB | 43 KiB |
| 权重缓存 | 4,608 B | 512 B | 19 KiB | 11 KiB |
| 输入 + 权重 | **17 KiB** | **5 KiB** | **78 KiB** | **54 KiB** |
| tile_sum 累加寄存器 | 16 B | 16 B | 96 B | 96 B |

因此，输入和权重局部缓存减少 **24 KiB（30.77%）**；tile_sum 的六核合计不变。BRAM 受端口组织与块深度取整影响，声明容量变化不等于物理 BRAM 容量变化。这个计算不减少共享特征图 SRAM 的地址空间或缓冲区分配。

## 整体综合状态

尚无当前十实例 CNN 顶层综合通过证据。已有的历史七实例顶层综合是 **FAIL**：Post 的 `params_reg` 无法推断 RAM，`Synth 8-3391` 报告 81,920 bit 存储不能按当前方式展开；DW7 同时有 `weight_mem_reg` 200,704 bit 三维 RAM 可能展开为寄存器的警告。
当前 Post、DW7 源码 SHA256 与这次失败记录相同。不能将单卷积核综合通过或全网算术仿真通过描述为整网资源、整体时序或上板已经验证。
上述估算未包含 DW7、Post、Add、Pad、固定流程编程器、调度、租约、结果交接、SRAM 及其仲裁逻辑。

## 可追溯报告

- [K3 综合结果](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/build/runs/20261023_150913_240097_self_cnn_synth/result.json>)
- [K1 综合结果](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/build/runs/20261023_151108_866766_self_cnn_synth/result.json>)
- [历史整体失败结果](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/build/runs/20261023_150436_706083_self_cnn_synth/result.json>)
- [资源与证据 SHA256 明细](</D:/zhang/fpga-cnn/cpu_control (2)/cpu_control/build/self_full_pool_review/resource_delta.json>)
