# C1：CNN→MOVER接口补充建议 v0.2

状态：CNN侧建议，待存储侧确认。这里没有映射CPU CSR，也没有分配PS物理地址。

## 1. 建议业务端口（相对于CNN）

| 信号 | 位宽 | 方向 | 语义 |
|---|---:|---|---|
| cmd_valid | 1 | 输出 | 命令有效，反压时全部字段保持稳定 |
| cmd_ready | 1 | 输入 | 与valid同拍时接收；单命令未完成/响应未消费前不接第二条 |
| cmd_src/cmd_dst/cmd_bytes/cmd_flags | 各32 | 输出 | byte地址/长度/控制；见下表 |
| rsp_valid | 1 | 输入 | 命令真正完成，或错误已确定；保持至ready消费 |
| rsp_ready | 1 | 输出 | CNN接收该完成响应 |
| rsp_status | 32 | 输入 | 成功/错误分类，编码建议见下 |
| rsp_bytes_done | 32 | 输入 | 成功等于请求长度；失败报告0，不提供可续传偏移 |

以上是业务接口，不是现有算子valid/ready/response本地存储端口。首版一条业务命令在途不禁止MOVER在该命令内部使用多个AXI突发/事务；完成必须覆盖命令全部事务。

| flags | src | dst |
|---|---|---|
| bit0=0：DDR_TO_LOCAL | DDR保留区byte偏移 | 本地RAM byte地址 |
| bit0=1：LOCAL_TO_DDR | 本地RAM byte地址 | DDR保留区byte偏移 |

flags[31:1]=0；未知控制位拒绝执行。layout/moves中的flags_proposed依据本候选编码，未代表存储RTL已经接受。

## 2. 对齐、长度与范围

- 本地允许任意byte起址，正整数bytes；每个字节精确复制，区间之外保持不变，由存储侧实现选通和拼接。
- 本包DDR起址均按8字节对齐，bytes可以不是8的倍数。任意DDR非对齐起址能力待另行回签，不能静默向下取整或越界扩大访问。
- 零长度建议报ERR_LENGTH，不访问内存；未知flags/非法范围也应在接受后返回明确错误，不进行静默截断。
- 使用足够宽的加法检查DDR offset+bytes、本地address+bytes以及configured_base+offset；范围右端是排他边界，不能32位回绕。
- DDR保留基址和长度由系统配置，样例的64KiB DDR镜像仅是测试范围，不是板上地址分配。

## 3. rsp_status建议编码

| 值 | 名称 | 含义 |
|---:|---|---|
| 0 | OK | 请求范围全部成功完成 |
| 1 | ERR_FLAGS | 未知flags |
| 2 | ERR_LENGTH | 零长度或非法长度 |
| 3 | ERR_RANGE | 越界、地址加法溢出 |
| 4 | ERR_DDR_ALIGNMENT | 当前版本不支持的DDR起址对齐 |
| 5 | ERR_AXI_READ | DDR读响应错误 |
| 6 | ERR_AXI_WRITE | DDR写响应错误 |
| 7 | ERR_TIMEOUT | 未在约定时间完成，仍需排空/恢复 |
| 8 | ERR_ABORTED | 由双方定义的停止/恢复流程结束任务 |
| 9 | ERR_FAULT_LOCKED | 存储仍处故障锁定，不能继续使用 |

编码仅供统一讨论。错误bytes_done=0不保证写操作原子性；可能存在部分数据已经修改。不得据此自动从0重试或释放原缓冲。

## 4. 完成、异常与复位

DDR→LOCAL成功需等本地RAM实际写入完成；LOCAL→DDR成功需等相关AXI B响应全部成功。本地算子done不代表DDR可见；所有下游消费者和必要写回完成后才能回收。

CNN在命令接受后等待其唯一响应；错误时锁存故障、停止新依赖任务并保护相关区域。超时不能伪造AXI事务取消。存储侧应明确排空/恢复状态的查询或握手方式（尚待定稿），未确认排空前不得复位后立即复用旧范围。旧响应必须与新一轮任务隔离。
