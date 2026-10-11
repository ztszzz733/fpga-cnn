# NEureka 大图仿真交付

先看 [波形阅读说明](波形阅读说明.md)，或打开 [六幅控制波形预览](index.html)。

双击 open_01_overview.cmd 查看全程，open_04_conv_write.cmd 查看卷积首次写回，open_05_pool_write.cmd 查看池化首次写回，open_06_complete.cmd 查看 CNN 与 CPU 完成。open_02_input.cmd 为 CPU 启动和输入搬运；open_03_conv_setup.cmd 为配置及卷积取数。每个视图信号不重复，按模块颜色区分。

本次为 SRAM 预加载，未经过 UART。详细接口只有 detail_valid=1 时记录，窗口外 X 表示未记录。PNG 从同一份真实 RTL 采样 VCD 绘制；六个 GTKWave 会话已实际加载检查通过，见 gtkwave_validation.log。

PASS：256×256 RGB → 254×254×8 卷积 → ReLU → 127×127×8 池化，核对 1,161,288 字节。

电脑执行仿真：2 小时 28 分 37.713 秒。成功脚本总耗时：2 小时 29 分 2.399 秒。硬件任务时间：101.60868 ms @100 MHz。本次重新编译 0 秒；复用程序的原始编译耗时 793.346 秒。

result.json 保存 PASS、源码哈希与计时；provenance.json 保存信号与时间窗口；sim.log 保存验证日志。运行来源：build/runs/20261011_153522_neureka。
