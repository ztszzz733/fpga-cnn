# 两 bank / 软件规划访存连接图

主文件：[EES331_两bank_软件规划访存_顶层连线图.drawio](EES331_两bank_软件规划访存_顶层连线图.drawio)。使用 draw.io / diagrams.net 的“打开现有图表”载入。全部方框、文字、连线均为可编辑图元，不是嵌入的整张图片。

采用旧版 `soc_top_view/soc_architecture.drawio` 的深色、方框分区和模块配色，连接以当前 RTL 为准，没有沿用旧版不存在的串口口、状态灯或指令下载口。

| 页 | 内容 | PNG | SVG |
|---|---|---|---|
| 01 | 六个 PL 功能模块、PS、J3、SD、DDR 顶层连接 | [预览](EES331_bank2_page1.png) | [矢量图](EES331_bank2_page1.svg) |
| 02 | 软件下发、K3 读段、两 bank 仲裁、返回流水、DMA | [预览](EES331_bank2_page2.png) | [矢量图](EES331_bank2_page2.svg) |
| 03 | 请求/返回的方向、信号名、位宽及 AXI3 通道 | [预览](EES331_bank2_page3.png) | [矢量图](EES331_bank2_page3.svg) |

图示配置：K3×2、PW8×4、Post×2、Add、Pad；10 路客户端；共享两 bank 各 196 KiB，共 392 KiB；IMEM 8 KiB；CPU Data SRAM 16 KiB。K3 自身四空间 MAC 使用的内部本地 bank 未缩减。

软件控制路径：ARM → GP0 邮箱 → RISC-V 固件 → CNN/Cache CSR。批量模型和图片经 PS DDR 存取；PL 中唯一 HP0 主设备是 DATA MOVER。J3 UART1 与 SD0 使用 PS MIO。

箭头按信号来源与接收方标注；混合方向接口分请求和回复线组，独立 READY 信号的方向见第 03 页。G 是共享时钟/复位网标签，不是新增模块。交叉线没有连接点时互不相连。

生成脚本：`docs/make_top_diagram.py`。预览和 draw.io XML 来自同一个几何模型；`diagram_validation.json` 记录 XML 引用、页边界、文字高度及连线不穿过无关模块框的检查结果，以及顶层源码哈希。

本版只通过功能仿真；100 MHz 是配置目标，图不代表综合、布局布线或板上验证已经通过。
