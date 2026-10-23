# 十张图片完整MobileFaceNet仿真

完整RTL PASS：十张不同112×112 RGB合成测试图，同一批次交错执行；1,310任务、2,338,104,320 MAC、193,372,920个写出字节逐值核对。十份128字节输出合计1,280字节，与独立整数参考完全一致；前六张输出也与上一轮完整六图RTL输出逐字节相同。

|时间口径|本次实测|
|---|---:|
|硬件周期|200,628,467拍|
|假设100MHz的整批时间|2006.28467ms|
|电脑模拟器主体|729.457秒|
|电脑运行总耗时，含初始化/收尾|754.292秒|
|本次全网重新编译|0.000秒|
|小门槛首次编译，另计|43.918秒|

电脑时间与硬件时间不同；100MHz只是换算条件，未进行整机布局布线或板级频率验证。生成输入与整数参考、报告处理时间另计。

## 查看十张图的并行

- [逐图片交互图](task_timeline/index.html)：**默认显示完整网络**。每张图片一行，拖动游标查看所有图片当时的层、算子和实例；可切换或自定义放大区间。
- [全部1,310任务](task_timeline/full_network.png)、[多实例并行放大](task_timeline/early_tasks.png)、[跨算子交接放大](task_timeline/cross_operator.png)。
- [真实MAC脉冲](mac_detail.png)、[跨类推进脉冲](pipeline_detail.png)，来自实际VCD，只有256拍局部窗口。
- GTKWave打开mac_detail.gtkw或pipeline_detail.gtkw；每个会话10根唯一信号。实际载入验证见gtkwave_validation.json。

跨图实际work重叠131,513,249拍；跨算子类别work重叠66,023,630拍。任务条包含访存等待，不能视为每拍MAC；实际work的K3/K1/DW7表示MAC推进，Post/Add/Pad表示接受写请求。八位置K1每拍可有1～8次MAC，Post/Add一次写最多四字节。

## 本次配置与数据流

两套K3（普通3×3/DW3共享）、四套八空间位置1×1、DW7/Post/Add/Pad各一套。使用原轮转调度，DW3优先关闭。十个在途上下文、40个工作缓冲槽、2,048条任务容量；CNN从单图131步模板和十份地址描述在RTL中展开1,310条任务，不是两批五图。

输入由TB经真实SRAM接口逐张写入，整张提交后该图计算，可与后续图片输入重叠；CPU固件、UART及同一图片的条带输入不在此测试内。每帧仍按层依赖顺序执行，多张图片共享算子池交错运行。中间结果经过SRAM，尚非层间直接流式融合。

仿真SRAM32MiB，初始化地址区29,694,464字节，尚未适配512KiB板级存储。前六张沿用之前的合成输入，新增四张确定性数值测试图。模型预训练权重不变，诊断量化尺度取首图并固定复用；不能据此宣称人脸识别准确率。图片数与K1结构同时改变，不能拿旧六图总耗时直接计算此次加速比。

## 波形信号

|信号|含义|
|---|---|
|unit_active[9:0]|调度器分配给各算子的任务仍在途，含内部访存等待|
|operator_work[9:0]|算子本拍MAC或写结果推进，位顺序K3#0/1、K1#0～3、DW7、Post、Add、Pad|
|mem_valid / mem_ready|各算子发起访存/互连接受请求，同拍为握手|
|mem_write|该请求为写回；低为读取输入、权重或参数|
|mem_response|互连向算子返回访存完成响应|
|frames_ready[9:0]|输入图像已写完并提交的十个标志|
|result_valid / result_ready|CNN发布结果描述/外部已读完结果并确认|
|completed_count[11:0]|已完成任务数，全程最终为1,310|

局部VCD时间从窗口起点计0，全程时间以events.csv和逐任务图为准，不能把窗口长度当整批计算时间。

输出SHA256：`16e732433489075ec40e78a83ebdf85f4123a84dcb1acb7a4124b421c6ffa418`。运行目录：`D:\code\FPGA1\cpu_control (2)\cpu_control\build\runs\20261024_014153_249128_self_ten`。
复现：scripts/gen_self_ten.py生成独立数据目录；run_self_six_wsl.py --frames 10 --pw8先跑build/self_ten_small四场景，完整通过后同程序--reuse --full --data build/self_ten_full --gate匹配小门槛目录。不得混用旧六图gate。

交付检查：五张PNG已视检；GTKWave实际载入两个会话均为10根唯一信号并通过。交互页JavaScript语法、十行数据和默认全程设置已静态校验；浏览器工具限制本地file协议，因此未做浏览器内预览。详见artifact_validation.json。
