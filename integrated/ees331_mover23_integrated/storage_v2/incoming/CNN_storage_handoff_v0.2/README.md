# CNN向存储侧补交材料 v0.2

请先看[分工与补充回复](docs/CNN侧补充回复_v0.2.md)和[C1接口建议](docs/C1_CNN_MOVER接口建议_v0.2.md)。

**CNN侧要求由存储侧MOVER处理本地非对齐byte访问；CNN保持紧凑HWC布局，不增加8字节对齐暂存拷贝。此为CNN侧回复，需存储侧回签。**

## 文件入口

- [主tile样例](cases/tile_8x8x32/README.md)：输入10×10×32，卷积→量化→Add输出8×8×32。
- [短行样例](cases/short_row_2x2x2/README.md)：输入4×4×2，输出2×2×2，每行4字节，第二行本地起址模8为4，DDR行跨度8字节。
- [96组非对齐期望向量](cases/unaligned_lane_vectors.json)：两个方向、8种本地byte lane、6种长度；供存储RTL接入，不是MOVER已验证结果。
- [已有16算子十图报告](evidence/ten_image_16_units/README.md)、[逐图交互图](evidence/ten_image_16_units/task_timeline/index.html)。完整副本包括原指标、输出、图表、来源哈希。
- source_snapshot保留当时算术RTL、完整测试台及哈希/编译参数；不含工具链和预训练大模型。

## 无第三方库的软件核对

在解压根目录执行：

```text
python tools/cnn_tile_handoff_case.py cases
```

脚本核对文件哈希、标量整数卷积/量化/Add、布局、搬运清单、完整DDR期望镜像和邻接字节。本地byte-copy是软件契约模型，不是存储MOVER RTL实现。golden不会预加载到native_fixture的结果区。

封包后可核对整个材料包（Python3.9或更新版本）：

```text
python tools/verify_cnn_storage_bundle.py .
```

## 真实算子RTL复核

本包复用已有16算子真实RTL测试台，配置十上下文但只激活一个tile，检查三个任务的每个写出字节、MAC数、响应排空、分配释放和保护区。它不覆盖新的MOVER或实际PS DDR。

Linux/WSL具备兼容Verilator和C++工具链时，可从源码重建：

```text
python3 tools/run_tile_handoff_rtl.py . --build
```

可用--verilator和--verilator-root指定工具链。若已有与build_signature.json中哈希完全匹配的可执行程序，也可使用--exe。为保留随包原始证据，脚本在已有evidence/tile_core_rtl时拒绝覆盖；复现请使用新的解压副本，先将该证据目录改名后执行。

## 当前未包含的验收

未提供存储侧MOVER RTL、CNN→新MOVER适配RTL、实际PS DDR验收或EES331同顶层资源/时序报告。当前已有独立算子/整网报告不能替代这些项目。旧十图报告中的原机器路径保留作来源记录；PNG和HTML可直接查看，GTKWave会话如含原路径需手动选择随包VCD。

最终状态和压缩包内哈希清单由封包检查生成。

补充范围：十图原始大数据和预训练模型未重复打包；完整网复跑仍需对应原数据，本包两个tile诊断向量自包含。native stress为现有SRAM端口冲突/慢速读回压力，不等于AXI随机反压或错误覆盖。

## 本次封包验证

两例各3种真实CNN/SRAM RTL场景全部PASS；主例逐场景检查12288输出字节、589824MAC，短行例检查48输出字节、144MAC。该检查绕过新MOVER。软件布局/整数参考/逐行复制检查PASS；96组非对齐向量已生成并由软件模型检查，等待存储RTL执行。

|场景|周期|结果|
|---|---:|---|
|short_row_2x2x2_overlap|1186|PASS|
|short_row_2x2x2_preloaded|544|PASS|
|short_row_2x2x2_stress|31316|PASS|
|tile_8x8x32_overlap|313518|PASS|
|tile_8x8x32_preloaded|248724|PASS|
|tile_8x8x32_stress|424935|PASS|
