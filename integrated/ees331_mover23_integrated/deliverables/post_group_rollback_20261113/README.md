# 仅撤销Post扩大分组

按最新要求，补边和Add保留。本次只将两个Post实例的GROUP_BYTES从32恢复16；Add仍为32，读取合并不变。1×1的输入面板复用、3×3的缓存优化和补边源码全部保持字节一致。

唯一生产修改为rtl/cnn_ddr/fixed_schedule_compact.sv中的实例参数：GROUP_BYTES(e==ADD?32:16)。共享后处理算术与Add缓存模块未修改，历史测试和修改前备份保留。

40个主用例及已有即时应答、尾部、地址重叠、非法参数、clear重启、描述符锁存、无复位复用检查通过。20个Post用例逐一复现最初16元素组的周期和请求数；20个Add用例逐一复现回退前优化版的周期、请求数及写入类型。

没有启动整图或重新综合资源。文件内记录的是当前选择的单元验证，不是整机PASS。

[复核记录](verification.json)、[测试结果](result.json)、[逐例指标](metrics.json)、[日志](simulation.log)。
