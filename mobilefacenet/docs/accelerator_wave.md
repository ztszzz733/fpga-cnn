# 纯阵列任务时序波形

在项目根目录运行：

```powershell
python mobilefacenet/scripts/accelerator_wave.py --open --view timing
```

脚本重新仿真当前RTL并打开GTKWave。9条任务全部为Conv/Depthwise，末层1×1卷积直接输出128个INT8特征。
不包含ReLU、ADD、COPY或独立FINAL_OUTPUT任务。
当前只有任务队列入口：所有exec_start均来自描述符FIFO握手，不存在MMIO直接启动算子的旁路。

生成文件位于 build/accelerator_wave/：

- timing.gtkw：任务切换、取数、计算、量化、写回、RAM等待、同拍有效PE数。
- timing_guide.md：每行含义、任务实际起止时间、间隔和建议放大位置。
- phase_cycles.csv：各阶段周期；RAM等待已包含在相应阶段中，不能重复相加。
- guide.md：各视图信号解释、任务参数。
- features_comparison.csv：最后128个值和写请求时刻。
- result.json：本次自动对照结果。

其他视图：--view overview 看任务概况；array看阵列；memory看RAM；output看结果提交。
不同任务顺序执行，同任务内部多个PE可以并行。目前没有跨任务计算并行，也没有取数与计算的双缓冲重叠。
final_output_issue表示最后一层卷积的输出请求，不是独立FINAL算子。
仿真使用10ns时钟，只表示调度周期关系，不代表芯片最高频率。
