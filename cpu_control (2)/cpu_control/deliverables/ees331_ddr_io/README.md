# EES331六模块加入DDR3后的IO接线图

后续实现：本图保留为用户确认的接线基线；对应 RTL 已新增，128 根信号已逐根核对，见 [代码入口与验证](../../docs/ees331_code_integration.md)。以下“待实施”描述是绘图交付时的状态，不代表当前代码仍未实现。

2026-10-24，**待实施接线方案**。保留原六个PL功能位置，并在同级画出PS硬核、板外DDR和电脑。图中的新模块名称、缓存维护接口和控制封装是拟定接口，不代表RTL已实现。

打开 [可编辑draw.io文件](ees331_soc_ddr_io.drawio)，优先看第02页改后总图；可在draw.io桌面版或diagrams.net中导入。所有模块、文字和连线均为原生可编辑单元，不是将PNG放进draw.io。

| 页码 | 内容 | PNG预览 |
|---|---|---|
| 01 | 改前：当前`face_soc_top.sv`六模块接线与板级IO | [改前总图](01_before.png) |
| 02 | 改后：六个功能位置、PS、DDR3及J3收图 | [改后总图](02_after.png) |
| 03 | 每条接口的地址组：信号名、方向、位宽 | [地址线](03_address.png) |
| 04 | 每条接口的数据组：写数据、读数据、DDR数据/写屏蔽 | [数据线](04_data.png) |
| 05 | 本地控制组：CPU、CNN、cache维护、请求/响应 | [本地控制线](05_local_control.png) |
| 06 | AXI3 GP0、HP0全部事务控制/属性/ID，逐根位宽 | [AXI控制线](06_axi_control.png) |
| 07 | DDR专用引脚、J3/PS UART、时钟与复位、改线说明 | [板级IO](07_board_clock.png) |

蓝色为地址，橙色为数据，绿色为控制/信号。`/N bit`标位宽；`→`相对于该接口定义的源端，`←`为返回，`<->`为物理双向。图上相反方向的数据以一个双箭头组表示，实际是独立的wdata/rdata线；DDR DQ/DQS才是物理双向。`io_connections.csv`及`io_manifest.json`保存可逐根核对的结构化列表。

## 原六模块如何变化

1. **CPU_CORE**：Control/Datapath保留，本地数据端口固定一拍。CPU的MMIO先接控制桥，原可达窗口内通过索引/数据寄存器访问邮箱和CNN；不假定原CPU可等待DDR或访问任意新增偏移。
2. **CNN**：从生产顶层的旧`mobilefacenet_accelerator_top`切换为已验证的新算子池，新增零等待寄存器封装和紧凑调度。CNN↔cache引出10组32bit地址/数据，即每组扁平总宽320bit，而非一条320bit DDR数据总线。
3. **DATASRAM**：同级位置保留，内部改为CPU本地RAM、CNN cache、仲裁/写回/DDR突发接口。CPU本地RAM16KiB、cache先128KiB/目标256KiB均为预算，未通过整机综合。
4. **IMEM**：端口名及32bit取指接口保留，建议容量64→8KiB，待正式固件链接结果确认。
5. **IMAGE_BRIDGE**：本次选择J3→PS路径，因此原PL UART收包/CRC移入PS程序；本位置拟改为`image_control_bridge`，包含PS GP0协议转换、邮箱、CPU侧零等待MMIO译码/转接。它不再通过旧`io_mem_*`路径搬运批量图片。若未来改选J8上口复用原UART，须另画该变体，不与本方案混编。
6. **CLOCK_UNIT**：统一选择PS FCLK供PL时钟，并同步释放复位；时钟复位在每个PL模块底部以同名全局网表示，第07页列出来源与去向。

新增使用 **PS7**：ARM负责DDR初始化、J3串口接收、CRC、DDR写入/可见性和结果回传；M_AXI_GP0控制PL邮箱，S_AXI_HP0接收cache的DDR读写请求。DDR1GB为板上现有存储，接PS专用DDR IO，未增加PL DDR管脚/MIG。

为了同原六模块层级直接对照，控制桥的AXI3→AXI Lite转换和DATASRAM的cache→AXI主接口在各自框内以文字注明，未另拆成顶层模块。CPU→控制桥→CNN MMIO仍为零等待寄存器访问；cache clean/fence是写命令后轮询状态，不能让CPU MMIO停到DDR写完。

## 接口边界与时序

- 原六模块页来自生产`face_soc_top.sv`，该页旧CNN只有单路`mem_*`。新CNN的10客户端来自`self_stream_top.sv`和bai存储接口，不能把新旧两种访存合同混用。
- `C`组`cnn_ready`表示接收，`cnn_response`表示后续返回；命中也至少延后一拍。`cnn_mem_fault`为cache向新CNN返回的全局故障。旧生产CNN没有fault输入，旧`cnn_mem_fault`仅参与顶层LED逻辑，图中已区分。
- `G`组是PS **M_AXI_GP0 AXI3 / 32bit数据 / 12bit ID**，协议转换在控制桥内；`H`组是 **S_AXI_HP0 AXI3 / 64bit数据 / 6bit ID**。AWADDR/ARADDR是两组独立32bit地址线，因此地址组总宽64bit，不表示64bit地址空间。
- HP0辅助FIFO计数/issue-cap信号列在第07页，事务握手全列在第06页。PL/AXI统一同一时钟，第07页明确两路AXI ACLK连接。若改用不同域需另补CDC。
- DDR接口方向按电路用途画：地址、命令和DM由PS到DDR；DQ/DQS物理双向。PS7生成的部分DDR端口在HDL中宣告为inout，这是专用IO封装形式，不改变图示功能方向。
- 输入DDR写完、PS缓存处理及PL旧行失效后才commit；结果dirty行写回DDR后PS才读；PC确认由CPU核对frame/epoch后释放结果。`F`组32bit CSR接口承载这些维护命令及状态，寄存器编码尚待实现时冻结。
- 同名全局网和重复出现在详图中的模块是同一实例，不是重复硬件。线交叉无圆点不连接。PS硬核与PL都在同一Zynq芯片内，只有DDR是板外芯片。

## 来源及检查

当前代码依据：`rtl/soc/face_soc_top.sv`、`rtl/soc/datasram.sv`、`rtl/soc/cpu_core.sv`、`rtl/soc/clock_unit.sv`、`rtl/cnn_stream/self_stream_top.sv`、`rtl/cnn_stream/bai/datasram_banked.sv`。PS接口名称/静态位宽以本机Vivado2026.1 `processing_system7_v5_5/component.xml`核对；HP0显式按64bit配置。DDR位置和J3/MIO48/49依据用户提供的EES331手册第10、15页。

生成器：`scripts/draw_ees331_ddr_io.py`。同一几何/标签模型生成draw.io、SVG和PNG，记录结构化接口与XML引用/文字边界检查；PNG供直接浏览，SVG供放大，draw.io供编辑。`diagram_validation.json`为图形结构验证，不是电路仿真结果。

本次仅绘图和细化接口方案，未修改计算RTL、运行全网、生成bitstream或推送GitHub。
