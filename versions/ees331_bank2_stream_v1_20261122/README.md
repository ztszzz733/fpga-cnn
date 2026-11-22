# ees331-bank2-stream-v1-20261122

这是当前简化四算子 CNN 的 **2 bank 连续读写恢复版 v1**。发布到 `bai-datasram`，开发源码基于 `zhang@b165edc`；本目录为独立工程快照，分支原有4 bank/任务图工程继续保留。

| 配置/结果 | 数值 |
|---|---:|
| 共享RAM | 392 KiB，2×196 KiB |
| 算子 | K3/DW3×2、K1×2，K1单输出通道 |
| 整机PL LUT / FF | **28,652 / 22,408** |
| BRAM Tile / DSP | **118 / 16** |
| 100 MHz综合WNS | **−0.078 ns，时序尚未通过** |
| 8个小任务集成仿真 | **83,550→37,745拍（−54.82%）**，结果一致 |

恢复了DMA与bank的连续请求、DDR写连续发送，以及每CNN单元四笔有序读取和两项输出写队列。输出完成和中止均等待已接受事务排空；同步暂存和返回寄存保留。

已验证82项DMA测试、160个CNN数值任务、4个非法描述符、4个中止重启单元、12项K1边界、10组访存桥测试、原分页器回归，以及真实CNN＋2 bank缓存＋DMA＋DDR模型的8任务小型集成测试。**上述性能来自小任务夹具；没有完整112×112网络、五图、旧ROM/ARM软件整机仿真、布局布线或上板结果。** 旧ROM/ARM PLAN仍需适配新MMIO；Post/Add/Pad/DW7未实例化。

## 入口与报告

- [最终工程源码](project/)；整机清单：[soc.f](project/simple_cnn/soc.f)。
- [完整仿真与综合报告](RESTORATION_REPORT_20261122.md)、[机器可读结果](RESTORATION_RESULTS.json)、[版本标识](VERSION.json)。
- [最终整机资源](evidence/synthesis/final/utilization.rpt)、[层级资源](evidence/synthesis/final/hierarchy.rpt)、[时序](evidence/synthesis/final/timing.rpt)。
- [源码哈希](project/source_manifest.json)、[发布文件哈希](PUBLICATION_MANIFEST.json)、[相对简化版的RTL差异](restore_streaming.patch)。
- `reference/`保留优化前与两个DMA中间版本；`evidence/`保留各阶段真实报告和原始仿真日志。历史报告内的本机绝对路径为证据记录，不是克隆后的构建路径。

## 复现

在本目录执行。默认使用Windows Vivado 2025.2及MSYS2 UCRT64 Verilator 5.050/g++；移机需调整工具路径。`scripts/verify_manifest.py`只核对发布文件，不运行仿真或综合。

```powershell
python scripts/verify_manifest.py
python scripts/run_bounded.py --seconds 240 --log build/final-integration-build.log --cwd . -- python scripts/build_test.py final integration
$integrationExe = (Resolve-Path build/final/integration/cnn_storage_top.exe).Path
python scripts/run_bounded.py --seconds 30 --log build/final-integration-sim.log --cwd build/final/integration -- $integrationExe
```

`build_test.py`测试选择为`dma/pager/cnn/bridge/integration`；版本选择为`baseline/stage1_local_stream/stage2_axi_stream/final`。仿真比较须使用同一测试程序和DDR模型。单独CNN边界检查可在构建后给`cnn_simple_top.exe`加`--k1-ranges`。

整机综合：

```powershell
$projectRoot = (Resolve-Path project).Path
$outputRoot = Join-Path (Get-Location) 'build/soc_synth'
python scripts/run_bounded.py --seconds 420 --idle-seconds 90 --log build/synth-console.log --cwd . -- D:/Xilinx/2025.2/Vivado/bin/vivado.bat -mode batch -log build/synth-vivado.log -journal build/synth-vivado.jou -source scripts/synth_soc.tcl -tclargs $projectRoot $outputRoot
```

限时器每20秒记录进展，连续90秒日志和CPU均无进展会中断进程树。资源未超限不代表已经完成时序或板级验证。
