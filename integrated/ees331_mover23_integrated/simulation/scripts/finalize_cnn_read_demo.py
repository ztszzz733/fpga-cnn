from pathlib import Path
import json,re
SIM=Path(__file__).resolve().parents[1];out=SIM.parent/'deliverables/cnn_read_demo_20261112'
r=json.loads((out/'result.json').read_text());s=(out/'verify.tcl').read_text()
s=re.sub(r'gtkwave::setZoomRangeTimes \d+ \d+','gtkwave::setZoomRangeTimes %d %d'%(r['first_return_ps']-100000,r['first_return_ps']+800000),s)
if 'DATA_VALID=' not in s:
 s=s.replace('close $log','puts $log "DATA_VALID=[gtkwave::getTraceValueAtMarkerFromName {CNN_READ.K1_0_READ_DATA_VALID}]"\nputs $log "READ_ADDR=[gtkwave::getTraceValueAtMarkerFromName {CNN_READ.K1_0_READ_ADDR[31:0]}]"\nputs $log "READ_DATA=[gtkwave::getTraceValueAtMarkerFromName {CNN_READ.K1_0_READ_DATA[31:0]}]"\nclose $log')
(out/'verify.tcl').write_text(s)
(out/'README.md').write_text('''# CNN 读数据示例

双击 open_reads.cmd。波形取自搬运优化后已通过的完整一图，不是新仿真。此处聚焦 K1_0，它对应原始 debug_* 向量的第 2 位。

- K1_0_READ_REQUEST：算子正在发出读请求，持续为 1 可能是在等内存接收。
- K1_0_READ_ACCEPTED：在该时钟上升沿，valid、ready 同为 1，write 为 0，读请求被内存系统接收。
- K1_0_READ_DATA_VALID：在该时钟上升沿，属于先前读请求的 response 被 CNN 采样。这个脉冲表示读数已到算子。
- K1_0_READ_ADDR：接受请求时锁存的逻辑地址。
- K1_0_READ_DATA：DATA_VALID 那一拍采样的数据，显示为十六进制。
- K1_0_READ_BYTES：该次读 4 字节或 1 字节。
- DDR_DATA_VALID：DDR 有返回数据；DDR_DATA_ACCEPTED 同时要求 RREADY。缓存命中时，CNN 仍可读数据而这两行保持为 0。

ACCEPTED、DATA_VALID、地址、数据均从真实原始信号按上升沿派生，方便读图，不是新增 RTL 引脚。原始 valid、ready、write、response 也列在底部供核对。response 同时用于读和写，因此派生 DATA_VALID 记住了请求被接受时的方向，不能只看返回时的 write 值。

默认游标指向第一笔读数被采样的时刻：地址 0x%08X，数据 0x%08X，4 字节；其 4 个字节按低位到高位排列。第一笔请求到数据被采样间隔为 %.2f 微秒，包含一次 DDR 页填充。后面的缓存命中读取明显更短。

本窗口包含 %d 笔已接受读请求和 %d 笔返回；窗口结尾有一笔尚在等待，属于局部截取边界。这里观察的是 CNN 对共享 RAM 的读取，不含卷积内部像素/权重 BRAM 的逐拍端口信号；计算阶段仍会从内部缓存读数。
'''%(r['first_address'],r['first_data'],(r['first_return_ps']-r['first_accept_ps'])/1e6,r['accepted_reads'],r['returned_reads']),encoding='utf-8')
print(out)
