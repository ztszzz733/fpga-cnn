# 算子间流水已回退

已恢复到开始加入卷积→后处理FIFO直连之前的代码状态。卷积先把INT32结果写入中间存储，后处理再读取并计算；原有算子分配与不同图片之间的并行保留。

## 撤销和保留

- 撤销独立卷积/后处理直连、8卷积共享2后处理后端、FIFO和元数据接口，以及合并任务6/7与软件融合规划函数。
- 9个原有文件逐字恢复到已保存备份；19个新实验文件移至可恢复归档，不从磁盘销毁。
- 保留此前K3/PW8数据复用、输入/权重缓存、PW8地址寄存器时序优化（ADDR_REGS默认1）、算子内部计算流水、Add的32字节分组、Pad优化及已有DDR/MOVER改进。
- 没有重新启用DSP映射，也没有修改时钟配置。恢复源码对应此前PW8独立时序验证版本，不等于整SoC已通过100MHz。
- 363个其他生产RTL、存储和固件文件的哈希与回退前一致。核验时发现公共compact_word_ram被历史源码快照误归类进归档，已按原哈希恢复，再完成全部回归；详见result.json的archive_correction。

## 验证

| 回归 | 主场景数 | 电脑执行耗时 | 结果 |
|---|---:|---:|---|
| pw8 | 129 | 24.781s | PASS，逐例指标与原记录一致 |
| k3 | 216 | 17.438s | PASS，逐例指标与原记录一致 |
| post | 40 | 1.312s | PASS，逐例指标与原记录一致 |

合计385个主数值场景及原测试中的协议/边界检查通过。复用的是全部源码哈希与当前版本完全匹配的旧编译程序，编译耗时0；新输出指标文件SHA256与原指标文件相同。程序哈希与原运行目录记录在[核验结果](validation.json)。

生产SoC入口face_soc_ees331_mover_top经system_ees331_reduced.f展开及语法检查通过；见[soc_lint.log](soc_lint.log)。没有重跑整图、完整网络、综合或布局布线。

## 恢复文件

| 文件 | 恢复目标SHA256 |
|---|---|
| rtl/cnn_self/self_pw8_engine.sv | `99e94b10cf431ad3a11094fab6983923fdd1218576ffef199cbb9b31de429685` |
| rtl/cnn_self/self_conv_spatial4_engine.sv | `15430f8b9af21d1efa1196a6152988edc5c7811e1e1c27078255031df1920a39` |
| rtl/cnn_quant/quant_post_pipe_engine.sv | `48b7275d3552857e7c0091141426f14443e4ccf3ec860ec29a05f7a15251e48b` |
| rtl\cnn_ddr\fixed_schedule_compact.sv | `80b9c62cc504c177d5f14cc67a454ce8dcdc1572c4454f1fde84666ba9e753ed` |
| rtl\cnn_ddr\cnn_ees331.sv | `4ecf5e28c4de7f1278c9330f9629e731cc0e41c1258a25dfd2d62faf4bd3c88e` |
| rtl\filelists\cnn_ees331.f | `67272278ff10ada65b1178b9b459de4ce40ddc6b9c5af4b191be08ca2d40aa7b` |
| rtl\filelists\system_ees331.f | `46191aa2bb96951baa4ad0788d7d08e313200f59817411b712b4ea985da1363e` |
| rtl\filelists\system_ees331_mover23.f | `27a7f1496d3b665cd31fe7481eba90347c4dd6ed7ca75f98d50c7f45a03c13cc` |
| rtl\filelists\system_ees331_reduced.f | `a18038dd407723bd999ddf1efdc7ffec9dc35bb3ab8976d8ae8bd2580c97576c` |

上表还原的是开始本轮算子间流水工作之前的版本，未回退更早的卷积内部优化。所有路径均位于当前生产工程。

## 归档与后续状态

回退前文件、19个实验文件和历史README片段保存在：`D:\code\FPGA1\integrated\ees331_mover23_integrated\simulation\build\runs\20261114_000147_rollback_operator_streaming`。新增文件位于其archived_files子目录，原有被改文件位于before子目录。历史波形和资源报告保留供对照，已增加ROLLED_BACK.md标记，不代表当前生产实现。

共享版LUT补测已取消，没有待自动执行的综合；先前39546 LUT只是试验关闭共享时的快速综合基准，不作为当前整机资源结论。之后若重新引入该实验，需要新的明确任务和版本核对，不能直接执行旧接续说明。
