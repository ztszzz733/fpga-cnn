GTKWave 波形免安装包（Windows 64 位）

1. 先把整个 ZIP 解压到一个文件夹。不要在压缩软件内部直接运行。
2. 双击最外层的 open_write_detail.cmd。
3. GTKWave 会自动打开，包含与前一张合并图相同的全部 36 根信号，
   默认放大到 CNN 四次输出写回这一段。

无需安装 GTKWave，无需管理员权限、Python、Vivado或联网下载。
GTKWave 程序、DLL 和库文件已一起放在 runtime 文件夹中。
请保留完整文件夹结构，不要只把 CMD 或 GTKW 单独拿走。

另外两个入口：
  open_all_signals.cmd  上电至计算结束的全程视图，仍含全部 36 根信号。
  open_cnn_detail.cmd   CNN 计算至 CPU 读回的放大视图，仍含全部 36 根信号。

波形数据在 waves/soc_wires.vcd，会话配置在 waves/*.gtkw。
waves/*.png 是已由 GTKWave 实际导出的截图，也可直接用图片查看器打开。
本包适用于 Windows x64，不是 macOS/Linux 应用包。

这仍是此前的 2×2 卷积演示，结果为 [5,-1,9,11]。
未改动 RTL，也没有把它冒充“外部只送图像”的后续实现。

工具：GTKWave 3.3.100 官方 Windows 便携版（并非声称是最新版）。
来源与版本说明见 THIRD_PARTY.txt。
可选自检：在本文件夹执行 open_write_detail.cmd --self-check；
结果保存在 verification/gtk_selfcheck.log。
