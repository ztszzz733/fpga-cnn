# NEureka 六模块接口图

用 draw.io / diagrams.net 打开 `neureka_soc_interfaces.drawio`，包含两页。所有模块、连线和文字均为可编辑对象，主模块端点已连接到对应方框。SVG/PNG 预览使用同一份布局。

第一页按参考图排列六大模块及数据接口；第二页展开时钟、复位、顶层状态和 LED 输出。蓝色为地址、黄色为数据、粉色为控制、红色为外部接口；标签 `/数字` 表示位宽。`we`、`be`、`rvalid` 等省略前缀的标签沿用同一条线上的 `io_mem_` 或 `cnn_mmio_` 前缀。

依据：`rtl/neureka/face_soc_neureka_top.sv` 及各实例的端口。本图描述当前实现，没有把讨论中的融合 ReLU 或流式池化画成已实现功能。CNN 内仍使用独立后处理任务；大图验证从 SRAM 预加载，未验证本顶层 UART 闭环。

CNN 与 SRAM 的 352 bit 地址/数据是 11 组 32 bit 客户端的展平总线，不是单次连续 352 bit 地址；valid、ready、write、byte、response 按客户端逐位对应。只有有效请求被接受时，write/byte/地址/写数据才有该笔事务的含义。

状态观察逻辑位于顶层，不增加第七个大模块。`cnn_mem_fault` 输出到顶层状态/LED 逻辑，不虚构其直接连入 CNN 的错误端口。`led_busy` 当前仅反映 IMAGE_BRIDGE 忙。

## 信号清单

| 信号 | 位宽 | 输出方 | 输入方 | 功能 |
|---|---:|---|---|---|
| imem_addr | 32 | CPU_CORE | IMEM | 取指地址 / 指令数据 / 读使能 |
| imem_rdata | 32 | IMEM | CPU_CORE | 取指地址 / 指令数据 / 读使能 |
| imem_re | 1 | CPU_CORE | IMEM | 取指地址 / 指令数据 / 读使能 |
| load_req | 1 | CPU_CORE | IMAGE_BRIDGE | 请求启动固定批次加载 |
| load_complete | 1 | IMAGE_BRIDGE | CPU_CORE | 加载完成握手及加载错误 |
| load_error | 1 | IMAGE_BRIDGE | CPU_CORE | 加载完成握手及加载错误 |
| dmem_addr | 32 | CPU_CORE | DATASRAM | CPU 数据读写；wstrb 按字节使能，读返回固定时序 |
| dmem_wdata | 32 | CPU_CORE | DATASRAM | CPU 数据读写；wstrb 按字节使能，读返回固定时序 |
| dmem_re | 1 | CPU_CORE | DATASRAM | CPU 数据读写；wstrb 按字节使能，读返回固定时序 |
| dmem_we | 1 | CPU_CORE | DATASRAM | CPU 数据读写；wstrb 按字节使能，读返回固定时序 |
| dmem_wstrb | 4 | CPU_CORE | DATASRAM | CPU 数据读写；wstrb 按字节使能，读返回固定时序 |
| dmem_rdata | 32 | DATASRAM | CPU_CORE | CPU 数据读写；wstrb 按字节使能，读返回固定时序 |
| cnn_mmio_addr | 32 | CPU_CORE | CNN | CPU 配置任务 / 读取 CNN 寄存器；ready 完成 MMIO 握手 |
| cnn_mmio_wdata | 32 | CPU_CORE | CNN | CPU 配置任务 / 读取 CNN 寄存器；ready 完成 MMIO 握手 |
| cnn_mmio_re | 1 | CPU_CORE | CNN | CPU 配置任务 / 读取 CNN 寄存器；ready 完成 MMIO 握手 |
| cnn_mmio_we | 1 | CPU_CORE | CNN | CPU 配置任务 / 读取 CNN 寄存器；ready 完成 MMIO 握手 |
| cnn_mmio_rdata | 32 | CNN | CPU_CORE | CPU 配置任务 / 读取 CNN 寄存器；ready 完成 MMIO 握手 |
| cnn_mmio_ready | 1 | CNN | CPU_CORE | CPU 配置任务 / 读取 CNN 寄存器；ready 完成 MMIO 握手 |
| cnn_addr | 352 | CNN | DATASRAM | 11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务 |
| cnn_wdata | 352 | CNN | DATASRAM | 11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务 |
| cnn_valid | 11 | CNN | DATASRAM | 11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务 |
| cnn_write | 11 | CNN | DATASRAM | 11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务 |
| cnn_byte | 11 | CNN | DATASRAM | 11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务 |
| cnn_ready | 11 | DATASRAM | CNN | 11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务 |
| cnn_response | 11 | DATASRAM | CNN | 11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务 |
| cnn_rdata | 352 | DATASRAM | CNN | 11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务 |
| cnn_cancel | 1 | CNN | DATASRAM | 11 路访存；valid/ready 接受请求，response 返回完成，write=1 写，byte=1 字节访问；cancel 清理待处理事务 |
| io_mem_addr | 32 | IMAGE_BRIDGE | DATASRAM | 加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求 |
| io_mem_wdata | 32 | IMAGE_BRIDGE | DATASRAM | 加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求 |
| io_mem_req | 1 | IMAGE_BRIDGE | DATASRAM | 加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求 |
| io_mem_we | 1 | IMAGE_BRIDGE | DATASRAM | 加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求 |
| io_mem_be | 4 | IMAGE_BRIDGE | DATASRAM | 加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求 |
| io_mem_rdata | 32 | DATASRAM | IMAGE_BRIDGE | 加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求 |
| io_mem_gnt | 1 | DATASRAM | IMAGE_BRIDGE | 加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求 |
| io_mem_rvalid | 1 | DATASRAM | IMAGE_BRIDGE | 加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求 |
| io_mem_error | 1 | DATASRAM | IMAGE_BRIDGE | 加载桥的 SRAM 读写接口；本版主动加载桥实际发写请求 |
| uart_rx | 1 | 外部 | IMAGE_BRIDGE | 外部 UART 串行数据 |
| uart_tx | 1 | IMAGE_BRIDGE | 外部 | 外部 UART 串行数据 |
| sys_clk | 1 | 外部 | CLOCK | 外部时钟 / 低有效复位 |
| rst_n_in | 1 | 外部 | CLOCK | 外部时钟 / 低有效复位 |
| clk | 1 | CLOCK | CPU_CORE / IMEM / CNN / DATASRAM / IMAGE_BRIDGE | 同名全局网，时钟直通及复位同步释放 |
| rst_n | 1 | CLOCK | CPU_CORE / IMEM / CNN / DATASRAM / IMAGE_BRIDGE | 同名全局网，时钟直通及复位同步释放 |
| cnn_status_busy | 1 | CNN | 顶层观察信号 | CNN 忙 / 完成脉冲 / 错误；不是顶层外部端口 |
| cnn_status_done | 1 | CNN | 顶层观察信号 | CNN 忙 / 完成脉冲 / 错误；不是顶层外部端口 |
| cnn_status_error | 1 | CNN | 顶层观察信号 | CNN 忙 / 完成脉冲 / 错误；不是顶层外部端口 |
| cnn_mem_fault | 1 | DATASRAM | 顶层状态及 LED 逻辑 | 访存故障；并未直接接入 CNN 的故障输入端口 |
| bridge_ready | 1 | IMAGE_BRIDGE | 顶层状态及 LED 逻辑 | UART 加载桥的就绪 / 忙 / 错误 |
| bridge_busy | 1 | IMAGE_BRIDGE | 顶层状态及 LED 逻辑 | UART 加载桥的就绪 / 忙 / 错误 |
| bridge_error | 1 | IMAGE_BRIDGE | 顶层状态及 LED 逻辑 | UART 加载桥的就绪 / 忙 / 错误 |
| led_ready | 1 | 顶层组合逻辑 | 外部 | 由本页公式组合生成；led_busy 不是 CNN 忙信号 |
| led_busy | 1 | 顶层组合逻辑 | 外部 | 由本页公式组合生成；led_busy 不是 CNN 忙信号 |
| led_error | 1 | 顶层组合逻辑 | 外部 | 由本页公式组合生成；led_busy 不是 CNN 忙信号 |
| cpu_state | 2 | 顶层观察状态机 | 仿真观察 | RESET=0 IDLE=1 WORK=2 FAULT=3；非功能控制反馈 |
| cnn_state | 2 | 顶层观察状态机 | 仿真观察 | RESET=0 IDLE=1 WORK=2 FAULT=3；非功能控制反馈 |
| sram_state | 2 | 顶层观察状态机 | 仿真观察 | RESET=0 IDLE=1 WORK=2 FAULT=3；非功能控制反馈 |
| imem_state | 2 | 顶层观察状态机 | 仿真观察 | RESET=0 IDLE=1 WORK=2 FAULT=3；非功能控制反馈 |
| bridge_state | 2 | 顶层观察状态机 | 仿真观察 | RESET=0 IDLE=1 WORK=2 FAULT=3；非功能控制反馈 |
| clock_state | 2 | 顶层观察状态机 | 仿真观察 | RESET=0 IDLE=1 WORK=2 FAULT=3；非功能控制反馈 |
| soc_module_state | 12 | 顶层观察逻辑 | 仿真观察 | 打包顺序高到低：CLOCK、IMAGE_BRIDGE、IMEM、DATASRAM、CNN、CPU_CORE |
| soc_active | 6 | 顶层观察逻辑 | 仿真观察 | 打包顺序高到低：CLOCK、IMAGE_BRIDGE、IMEM、DATASRAM、CNN、CPU_CORE |
| soc_fault | 6 | 顶层观察逻辑 | 仿真观察 | 打包顺序高到低：CLOCK、IMAGE_BRIDGE、IMEM、DATASRAM、CNN、CPU_CORE |
