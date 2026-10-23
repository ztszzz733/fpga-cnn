# 六图完整网络：第三轮优化验证

完整RTL仿真PASS。六张112×112 RGB合成图片，同批交错执行完整MobileFaceNet，总共786任务、1,402,862,592 MAC；116,023,752个写出字节通过逐值检查，最终768字节与原版及整数参考完全一致。

## 加速结果

|范围|对照|优化后|
|---|---:|---:|
|完整六图硬件周期|898,010,175|153,487,331|
|假设100MHz，六图整批时间|8.980102秒|1.534873秒|
|六图小回归（仅本轮与上一轮比较）|263,887拍|239,519拍|

完整批次周期减少 **82.91%**，同频批次速度为 **5.85倍**。完整对照是原始六图版本，包含四位置K1、K1搬运重叠、K3计算流水及本轮宽读取/后处理的累计收益；不是把全部收益归给本轮改动。小回归本轮再减少9.23%，不能单独外推成全网收益。

本次电脑执行总耗时 **386.188秒**，其中模拟器主体374.345秒。本次复用小回归程序，重新编译0秒；小门槛首次编译51.970秒。不含此前开发、单测、综合和历史失败尝试，电脑耗时不是硬件时间。

## 看并行与数据流

- [六张图片逐任务交互图](task_timeline/index.html)：每张图一行，移动同一时间游标查看各图正在执行的层和算子。
- [跨算子交接放大图](task_timeline/cross_operator.png)、[卷积并行区间](task_timeline/early_tasks.png)、[全部786任务](task_timeline/full_network.png)。色块含访存等待。
- [完整六图前后比较](full_comparison.png)。
- [实际MAC脉冲](mac_detail.png)与[跨算子推进脉冲](pipeline_detail.png)：来自真实VCD，不是任务条模拟波形。
- GTKWave打开`mac_detail.gtkw`或`pipeline_detail.gtkw`，各10根唯一信号；实际载入验证结果见`gtkwave_validation.json`。

本次跨图实际work重叠119,334,705拍，跨类work重叠47,098,777拍。K3/K1/DW7的work为MAC推进，Post/Add/Pad为接受写请求；新Post/Add可一次写四个字节，不能将写脉冲数量下降误解为少算了元素。窗口只有相对起点256拍；全网起止看events.csv，不能将局部波形长度当全网时间。

## 结构与边界

仍为K3×2、K1×4，DW7/Post/Add/Pad各1；没有加倍算子。K3缓存复用不变，新增对齐四字节读取；Post/Add改为七级计算流水和四元素打包写，保留字节尾部及精确舍入。跨算子数据仍写入共享SRAM；尚未做卷积到后处理直接融合或同帧层内条带流水。

K3单模块OOC为2033 LUT、1528 FF、6 BRAM Tile、0 DSP，WNS+0.147ns；Post流水为1092 LUT、848 FF、2.5 BRAM Tile、8 DSP，WNS+2.674ns（Z7020/10ns）。这是独立综合，不是整机布局布线或已实现100MHz。详细证据在optimization_evidence。

输入由测试台经真实SRAM接口写入，整图提交后计算，可与后续图片输入重叠；没有UART或CPU固件参与。合成图片、诊断量化不能证明识别准确率。32MiB仿真SRAM尚未适配512KiB。输出SHA256：`9e4b5e7edf785b32a7c60d12cee48ac038c7e74403129982d8047b4b7440fcdf`。

运行目录：`D:\code\FPGA1\cpu_control (2)\cpu_control\build\runs\20261024_003528_447842_self_six`。设计和复现说明：[wide_pipe_design.md](../../docs/wide_pipe_design.md)。
