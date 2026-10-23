# 自研卷积替换：双图小规模验证

2026-10-23，基于 GitHub `zhang` 分支提交 `7720bcac91771696dd7aa2ebdd8b42226a0a1ec9`。本轮按用户新范围实现：**3×3 两套，其余每类算子一套**；用户再次明确已有算子复用，替换 NEureka 大卷积。

**第一阶段真实 RTL 双图验证通过，完整 CNN 综合未通过。** 测试输入是两张不同的 7×7 RGB 合成图片，使用诊断权重。每张图经过 Pad → 普通3×3 → Post/ReLU → Pad → DW3 → Post/限幅 → 1×1 → Post → 残差Add → DW7 → Post，最终各产生8字节。它验证算术、双图并发和交接，不是完整 MobileFaceNet 的128维人脸特征。

## 文件入口

- [新 CNN 顶层](../../rtl/cnn_self/self_network_top.sv)、[自研卷积](../../rtl/cnn_self/self_conv_engine.sv)、[独立编译清单](../../rtl/filelists/cnn_self.f)。清单没有 NEureka 或第三方算术依赖。
- [接口、命令、缓存和清除契约](../../docs/self_cnn_interface.md)。CPU、外部接收、生产 DATASRAM 的联调另行进行。
- [验证报告](verification_report.md)、[全部测试结果](result.json)、[单元结果](unit_result.json)、[参数覆盖结果](parameter_review.json)。
- [架构图](architecture.drawio)、[全程波形](overview.png)、[双 MAC 重叠](dual_mac.png)、[第一次卷积写回](conv_write.png)、[后处理写回](post_write.png)、[最终结果确认](result_ack.png)。GTKWave 会话与打开脚本在本目录，原始波形为 `dual/control.vcd`。

## 实例清单

| 实例 | 数量 | 实现及有效活动 |
|---|---:|---|
| 普通3×3 / DW3 | 2 | 新 `self_conv_engine`，每实例一条MAC，动态分配 |
| 1×1 | 1 | 同一自研RTL，K1专用配置 |
| DW7 | 1 | 复用原 `dw7_cached_engine` |
| 量化、偏置、ReLU/限幅 | 1 | 复用原 `quant_post_engine` 的Post模式 |
| 残差Add | 1 | 原 `quant_post_engine` 的另一个独立实例，Add模式 |
| 补边 | 1 | 复用原 `pad_hwc_engine` |

共七个独立执行实例。3×3池中的每个实例均能执行普通卷积和DW3，两个实例共同服务两张图片。1×1、DW7、Post、Add、Pad可与3×3重叠。Post和Add可彼此独立推进。

## 复现

在 `cpu_control (2)/cpu_control` 目录运行，使用本机已有 Python 和 Vivado XSim；不需要 WSL：

```powershell
python scripts/test_self_conv.py
python scripts/run_self_pair.py
python scripts/prepare_self_pair.py build/runs/20261023_150822_041360_self_pair
```

`run_self_pair.py` 一次编译后运行十个场景。`--reuse <既有run目录>` 仅在源码哈希匹配时复用编译；`--images 图片1 图片2` 可换输入，测试脚本会将图片缩小到7×7。当前人脸参考模型和文档中的 `D:/code/facemodel/person_*.jpg` 未随本次克隆提供，不能以本轮合成图测试替代这些资源。

```powershell
python scripts/synth_self_cnn.py
python scripts/synth_self_cnn.py --top self_conv_engine --max-kernel 3
python scripts/synth_self_cnn.py --top self_conv_engine --max-kernel 1
```

第一条尝试完整七实例综合，当前已知会被旧Post参数RAM的推断错误阻断，日志已保留。后两条仅综合一个新卷积模块，不能替代整体资源报告。没有启动完整大图长仿真。

## 下一阶段

先修复旧 DW7/Post 和调度表的 RAM 推断与资源组织，取得完整七实例的资源/时序报告并给CPU预留预算。再取得原模型及人脸输入，适配新权重布局和完整图的有界任务窗口，完成完整单图、完整双图验证。分条带接收、跨层块级流水、连续N帧、生产存储接入及准确率验收仍是后续工作。
