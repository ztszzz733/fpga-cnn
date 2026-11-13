# DW7独立资源统计

**本次仅统计DW7，其它模块已按用户要求停止。**

配置与当前CNN一致：MAX_WIDTH=7、MAX_CHANNELS=512、LANES=8、reuse_weights=0；8位无符号输入×8位有符号权重，32位累加输出。使用真实RTL及临时常量绑定包装，功能RTL没有修改。

Vivado 2025.2 / XC7Z020-CLG484-1，OOC综合，flatten_hierarchy=none，1线程，仅资源报告，无布局布线和100MHz时序保证。其它模块没有同时综合。

最终状态：**MEMORY_GUARD**；本机执行536.297秒。

**未取得最终LUT/FF/BRAM/DSP数值，不能填0，也不能把日志里的数组位数当最终寄存器数。**

TIMEOUT表示900秒内未完成；MEMORY_GUARD表示本机可用物理内存低于1.5GiB而停止；FAIL需以具体错误为准。未更改512通道配置、未偷偷裁减模块或用小配置外推。

日志提示weight_mem_reg是200704位的多维权重数组，存在综合处理问题。该提示不证明最终映射成200704个FF，也不是最终资源报告。当前实际声明容量为权重25088字节（24.5KiB）、行缓存392字节、8个32位累加器；这些是RTL逻辑容量，不是已测物理资源。

- [本次原始结果](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261109_195054_407075_missing_resources/result.json>)
- [DW7日志](<D:/code/FPGA1/cpu_control (2)/cpu_control/build/runs/20261109_195054_407075_missing_resources/dw7/process.log>)
- [当前DW7源码](<D:/code/FPGA1/cpu_control (2)/cpu_control/rtl/cnn_quant/dw7_cached_engine.sv>)
