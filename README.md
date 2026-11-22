# FPGA CNN 工程

## 当前发布：2 bank 连续读写恢复版 v1（2026-11-22）

工程与报告入口：[ees331-bank2-stream-v1-20261122](versions/ees331_bank2_stream_v1_20261122/README.md)。

完整PL综合：**28,652 LUT、118 BRAM Tile、16 DSP**，资源未超限；100 MHz综合WNS为**−0.078 ns**，尚未完成时序收敛。8个小任务的CNN/缓存/DMA集成仿真输出匹配；完整网络与旧ROM/ARM软件仍需适配。

原有工程保留在 [integrated/ees331_mover23_integrated](integrated/ees331_mover23_integrated/) 和 [releases](releases/)，配置与本版不同，报告需按具体版本使用。
