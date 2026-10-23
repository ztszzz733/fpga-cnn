# 六张完整图片 MobileFaceNet 仿真

本次完整 RTL PASS：786任务，6份128字节输出，MAC总数 1,402,862,592，输出逐字节匹配独立整数参考。

当前配置 K3×2、K1×4，DW7/Post/Add/Pad各1；六帧同批次交错处理，不是4+2分批。

- 编译：0.000 秒（本次复用小数据门槛程序）。小回归首次编译65.270秒。
- 本次电脑执行：1817.888 秒；硬件周期 898,010,175。
- 假设100MHz硬件时间：8980.10175 ms，不代表已验证板级频率。
- 跨图实际工作重叠：482,753,085 拍；跨类工作重叠：60,362,645 拍。
- 输出SHA256：`9e4b5e7edf785b32a7c60d12cee48ac038c7e74403129982d8047b4b7440fcdf`。

输入为6张不同合成112×112 RGB数值测试图，完整预训练MobileFaceNet运算。首图诊断量化尺度固定复用，不能证明人脸识别准确率。输入由TB通过真实SRAM接口逐张写入，整张提交后该帧开始计算；不是UART、CPU固件接入或层内条带流水。

仿真SRAM为32MiB，初始化区18,302,464字节；未解决512KiB生产存储适配。

`frame_timeline.png`显示真实帧时序。`mac_detail.gtkw`与`pipeline_detail.gtkw`分别观察实际MAC与跨类工作，10根唯一信号。VCD只覆盖256拍局部窗口，横轴起点为窗口相对零点，不是全网启动时间；全程事件见events.csv。unit_active含等待，operator_work表示有效运算/推进；mem_valid/ready/write/response表示各实例存储握手；frames_ready为六帧输入就绪位；result_valid/ready为结果发布/读完确认；completed_count为任务完成数。

运行目录：`build\runs\20261023_215237_self_six`。保留原四图交付不覆盖。GTKWave实际载入校验通过：两会话各10根唯一信号，见gtkwave_validation.json。

## 查看波形

- [六帧时序](frame_timeline.png)：首次发射到结果读完，含等待。
- [双卷积实际计算](mac_detail.png)：K3 #0和#1的work脉冲重叠。
- [跨算子工作](pipeline_detail.png)：K3与Pad的work同时推进。
- 在GTKWave中打开同名.gtkw可展开总线；PNG为真实VCD绘制，不是GTKWave截图。

电脑仿真主体1809.05秒，含初始化和收尾总1817.888秒（30分17.888秒）；不含首次编译。全程跨图片实际work重叠占53.76%，并非每个算子都始终忙。六图没有做全网串行对照，不能据此宣称六倍提速。

## 按图片查看每段时间的任务

新版请先看 [逐任务并行图说明](task_timeline/README.md)、[前1000ms](task_timeline/first_1000ms.png) 和 [交互时间线](task_timeline/index.html)。每张图片一行，每块标注网络层、运算类型和执行实例，比原整帧长条更具体。
