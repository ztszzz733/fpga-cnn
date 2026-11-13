# PW8地址生成时序优化核验（2026-11-13）

PW8单模块内部已约束时序通过10ns检查。 本次仅改1×1卷积PW8的地址生成，未增加计算流水级、MAC数量或RAM容量，DSP保持0。129个数值场景和额外协议回归全部通过；所有129场景的周期数、外存请求数、读字节数逐项与优化前相同。

## 改了什么

此前从微块编号load_slot组合译码行列，再串联多个32位加法生成load_addr；综合最差路径是load_slot_reg到load_addr_reg，WNS=-1.087ns。

现在增加输入/输出微块原点及行原点四个32位寄存器，切换微块时累加行或列步长。地址计算分散到已有状态，取消同一拍里的多级地址推导。保留8路MAC、输入预取、权重整层/双缓冲复用、输入panel复用、写FIFO。参数ADDR_REGS默认1，设0可使用原始地址公式。

## 资源（同一口径的单PW8综合）

器件xc7z020clg484-1，MAX_CHANNELS=512，kernel固定1，其余描述符输入保留，Vivado 2025.2，10ns时钟，单线程。

| 资源 | 修改前 | 修改后 | 增减 |
|---|---:|---:|---:|
| LUT | 3073 | 3005 | -68 |
| FF | 1722 | 1849 | +127 |
| BRAM36等效块 | 1.5 | 1.5 | +0 |
| DSP | 0 | 0 | +0 |
| 其中LUT RAM | 44 | 44 | +0 |

按6套PW8简单相乘，估计合计LUT减少408、FF增加762；这不是整机重新综合结果。新模块布局布线后资源为LUT 2973、FF 1849、BRAM 1.5、DSP 0，不能把它与旧综合资源直接当同阶段比较。

## 时序

| 阶段 | 修改前WNS | 修改后WNS |
|---|---:|---:|
| 综合估算，同口径 | -1.087ns | +0.226ns |
| 新版单模块实际布局布线 | 本次未跑旧版布局布线 | +0.025ns |

新版布线后WHS=+0.028ns、WPWS=+3.750ns；setup/hold/pulse失败端点分别为0/0/0。具体路径见[布线后时序报告](implemented_timing.rpt)。新版最差路径已变为panel_w_reg[1]到load_addr_reg[23]，数据路径9.830ns；+0.025ns的建立裕量非常小，不能认为具有充足余量。

这是out-of-context单模块内部时序验证。报告中无时钟寄存器和未约束内部端点均为0；294个输入、171个输出未指定输入输出延时，外部端口也未指定板级位置，端口路径不构成整机闭合证明；Vivado提示OOC时钟源/端口位置限制。未验证CNN互联、DDR/MOVER、CPU及整SoC的布局布线，不能据此保证整机上板100MHz。

## 功能和性能核验

- 129个数值场景：输入通道1～512，步长1/2，对齐/非对齐，边缘微块，权重缓存边界，panel多微块；含28×28×64和28×28×128。
- 与标量参考逐字节比对，检查写覆盖、越界和MAC总数；额外覆盖clear/restart、运行中改变描述符、非法配置、即时响应、同地址更新输入/权重后再次启动。
- 优化前后129场景的周期数、请求数、读取字节数全部一致；ADDR_REGS=0也复现旧版。此次收益是改善时序和减少少量LUT，不是减少卷积周期。
- 未运行整图/完整网络，也未宣称网络加速比例。K3、Post、Add、Pad相关文件哈希保持原样。

## 执行时间与内存

小回归编译19.526s，执行10.830s；本次成功综合83.328s，布局布线118.172s，均为电脑实测时间。

首次综合因系统可用内存低于1.5GiB被保护停止，保留在C:\Users\windows\.codex\visualizations\2026\10\09\01a11f57-abad-73d3-bace-ffb2cb9844cd\resource_pw8_addr_20261113_202721，不当作成功。释放内存后分成独立综合与布局布线两个进程，每阶段保存结果，起始可用内存分别5.05/5.01GiB，未停止其他任务。

## 证据与复现

- [功能回归结果](regression_result.json)、[逐例指标](regression_metrics.json)、[日志](regression.log)。
- [资源及时序汇总](resource_result.json)、[综合利用率](utilization.rpt)、[综合时序](timing.rpt)、[布线后利用率](implemented_utilization.rpt)。
- [代码差异](address_change.diff)、[变更与保留文件哈希](change.json)。本目录保留测量源码快照及Tcl脚本。
- 优化前PW8 SHA256：`690e7f0127449441f5e67e5ddf5a38112e37155bc4fda92e08d74ee2218de01b`。
- 优化后PW8 SHA256：`99e94b10cf431ad3a11094fab6983923fdd1218576ffef199cbb9b31de429685`。
- 生产源码：`rtl/cnn_self/self_pw8_engine.sv`；回归脚本：`simulation/scripts/run_pw8_addr_unit.py`（在现有WSL/Verilator环境中运行）。
- 实际资源运行目录：`C:\Users\windows\.codex\visualizations\2026\10\09\01a11f57-abad-73d3-bace-ffb2cb9844cd\resource_pw8_addr_retry_20261113_203458`；综合/布线DCP仍保留于该目录，避免重复复制大文件。
