# Datapath 代码合并与 B1 存储接口适配报告

文档编号：`FACE-SOC-DP-MERGE-B1`  
日期：2026-09-29  
面向：CPU Datapath / SoC 集成负责人  
结论：负责人原始 Datapath RTL 保持不变；项目所需的实体存储器、B 口仲裁、CNN MMIO 和连接顶层已作为隔离新增文件加入交付副本，并通过 XSim 验证。

## 1. 输入代码和隔离方式

本次输入包为：

```text
D:\QQ\face_recognition_soc_datapath_complete.zip
SHA-256:
7DCAD4FB247B2B12A172009B63FD2F8C5506DBD57F4107793C95A4EB77ECD91C
```

工程内采用两份目录，避免适配工作污染原始交付：

```text
partners/datapath/
├─ upstream_20260917/   原包解压基线，只用于比对
└─ delivery/            当前可修改、可测试、可回传的 Datapath 包
```

已逐文件比较 `upstream_20260917` 中的 43 个文件与 `delivery` 中的对应文件：

```text
原始文件数：43
缺失文件数：0
内容变化数：0
```

也就是说，本次没有直接改写负责人的 `cpu_datapath.sv`、流水寄存器、LSU、地址译码、寄存器堆或原测试代码。所有项目适配均使用新增文件实现，方便负责人只接收属于 Datapath/存储侧的内容。

## 2. 与当前项目设计的对比结果

### 2.1 已经一致的部分

负责人代码与当前项目的 C1 / D1 基线已经满足以下关键点：

- `cpu_datapath` 与正式 `cpu_control` 的 48 个接口名称、方向和位宽匹配。
- Control 保持组合逻辑；PC、寄存器堆和四组流水寄存器都由 Datapath 保存。
- CPU Data SRAM A 口为 32 位地址、32 位写数据、4 位字节使能、读写控制和 32 位返回数据。
- Data SRAM 读采用固定一周期同步时序，没有增加 `ready/rvalid`，不会改变现有流水线契约。
- SRAM 默认窗口是 `0x0000_0000`～`0x0003_FFFF`，共 256 KiB。
- CNN MMIO 默认基址是 `0x4000_0000`，窗口为 4 KiB。
- Datapath 在 EX→MEM 边沿提交 SRAM 访问，在 MEM 周期使用返回数据；CNN MMIO 在 MEM 级访问。
- 负责人提供的兼容 package 完整保留了 Control C1 的数值编码，并以别名补充 Datapath 所需名称。集成时只编译这一份同名 package。

### 2.2 原包与当前项目要求之间的缺口

| 当前项目要求 | 原包情况 | 本次处理 |
|---|---|---|
| 可综合的片内指令存储器 | 只有 test-only IMEM model | 新增 `imem_rom.sv` |
| 可综合的双口 Data SRAM | 只有 test-only DMEM model，且没有正式 B 口 | 新增 `data_sram_tdp.sv` |
| 外部图像 IO 与 CNN 共用 B 口 | 没有双主设备仲裁器 | 新增 `sram_b_arbiter.sv` |
| B 口每个主设备必须有 70 位请求、35 位响应，且保留 `error` | 原包没有该正式接口 | 已按 B1 实现 |
| 可综合的 CNN MMIO 寄存器 | 只有 test-only MMIO stub | 新增 `cnn_mmio_regs.sv` |
| 正式 Control、Datapath 与存储器的连接层 | 原包只提供 Datapath 顶层 | 新增两个集成层和工程级 filelist |
| FPGA 外部图像物理接口 | 原包没有 `image_io_bridge` | 本次只保留标准 B 主设备端口，物理 UART/摄像头桥仍由对应负责人实现 |
| 真实 CNN DMA/计算模块 | 原包没有 | 本次只保留 CNN B 主设备和 MMIO 状态端口，不伪造 CNN 内部 RTL |

原包 README 中“尚未连接真实 Control”的描述属于原包独立验收阶段。当前工程已经用正式 Control 对生产 Datapath 做过 ADD 和混合程序验证，但这仍不等于真实 CNN 或整块 FPGA 板级联调完成。

## 3. 本次新增文件

| 文件 | 作用 |
|---|---|
| `rtl/soc_memory/imem_rom.sv` | 64 KiB 默认容量、固定一周期同步读的指令 ROM；支持 `INIT_FILE` 在 FPGA 配置时预装程序 |
| `rtl/soc_memory/data_sram_tdp.sv` | 256 KiB 默认容量的双口 Data SRAM；A 口给 CPU，B 口给仲裁器 |
| `rtl/soc_memory/sram_b_arbiter.sv` | 在图像 IO 和 CNN 之间仲裁 Data SRAM B 口；CNN 固定高优先级，并保存未完成读请求的 owner |
| `rtl/soc_memory/cnn_mmio_regs.sv` | CONTROL、STATUS 和七个配置寄存器；CONTROL 为单周期脉冲，STATUS 只读 |
| `rtl/soc_memory/datapath_memory_subsystem.sv` | 把 Datapath 的 IMEM、A 口、MMIO 接到上述实体，并把两个 B 主设备接到仲裁器 |
| `rtl/soc_memory/face_soc_cpu_memory_top.sv` | 实例化正式 `cpu_control`、生产 `cpu_datapath` 和存储子系统，形成当前 CPU+存储连接边界 |
| `rtl/filelists/datapath_b1.f` | Datapath 交付侧的 B1 源文件清单 |
| `tb/unit/tb_b1_memory_subsystem.sv` | B1 存储、仲裁和 MMIO 独立测试 |

工程根目录另有 `rtl/filelists/system_partner_datapath_b1.f`。它先编译 Datapath 交付包内的兼容 package，再编译正式 Control、生产 Datapath 和新增存储模块，避免同时编译两份 `cpu_control_pkg.sv`。

## 4. 合并后的连接关系

```text
                         ┌──────────────────┐
                         │   cpu_control    │
                         │ 组合译码/冒险控制│
                         └────────┬─────────┘
                                  │ C1 48 根接口中的控制/状态连接
                         ┌────────▼─────────┐
                         │   cpu_datapath   │
                         │ PC/寄存器/流水线 │
                         └───┬────┬─────┬───┘
                    IMEM     │    │A口  │MMIO
                 ┌───────────┘    │     └─────────────┐
          ┌──────▼──────┐   ┌────▼─────────┐   ┌─────▼─────────┐
          │  imem_rom   │   │data_sram_tdp │   │ cnn_mmio_regs │
          │程序固化在FPGA│   │      A/B      │   │ CNN控制/状态   │
          └─────────────┘   └──────▲───────┘   └─────┬─────────┘
                                   │B口              │配置/状态
                          ┌────────┴────────┐         │
                          │ sram_b_arbiter  │         │
                          └───────▲────▲────┘         │
                                  │    │              │
                     image_io_bridge   cnn_accelerator
                         图像输入/输出     DMA/计算
```

`face_soc_cpu_memory_top` 没有软件在线下载接口。CPU 程序通过 `IMEM_INIT_FILE` 在综合/生成 bitstream 时固化；运行时外部图像和结果数据只经 Data SRAM B 口进出，符合当前“CPU 不接受外部软件控制”的要求。

## 5. Data SRAM 接口和位宽

### 5.1 CPU A 口

请求方向共 70 位：

```text
a_addr(32) + a_wdata(32) + a_wstrb(4) + a_re(1) + a_we(1) = 70 bit
```

返回方向：

```text
a_rdata(32) = 32 bit
```

连接关系保持为：

```text
cpu_datapath.dmem_addr  -> data_sram_tdp.a_addr
cpu_datapath.dmem_wdata -> data_sram_tdp.a_wdata
cpu_datapath.dmem_wstrb -> data_sram_tdp.a_wstrb
cpu_datapath.dmem_re    -> data_sram_tdp.a_re
cpu_datapath.dmem_we    -> data_sram_tdp.a_we
data_sram_tdp.a_rdata   -> cpu_datapath.dmem_rdata
```

### 5.2 图像 IO 和 CNN 的 B 主设备口

每一个主设备都有一套独立请求，共 70 位：

```text
mem_req(1) + mem_we(1) + mem_addr(32) + mem_wdata(32) + mem_be(4) = 70 bit
```

每一个主设备都有一套独立响应，共 35 位：

```text
mem_gnt(1) + mem_rvalid(1) + mem_rdata(32) + mem_error(1) = 35 bit
```

`error` 没有删除。非法地址、非 4 字节对齐、非法 byte enable 或 A/B 同字冲突都会完成事务并报告错误，避免主设备无限等待。

### 5.3 仲裁和冲突规则

- 没有未完成读请求时，CNN 优先于图像 IO。
- 接受读请求后保存 owner，收到 SRAM 的 `rvalid` 前不接受新请求。
- 返回数据、`rvalid` 和 `error` 只送给保存的 owner。
- A、B 访问不同字可以并行；同字读/读允许。
- A 写与 B 同字读/写冲突，或 A 读与 B 同字写冲突时，A 优先，B 返回 `error=1` 且不产生 B 口副作用。

## 6. CNN MMIO 寄存器

| 地址 | 名称 | 属性 | 连接方向 |
|---:|---|---|---|
| `0x4000_0000` | CONTROL | W1P | CPU 写；`[0]` start、`[1]` soft reset，只保持一周期 |
| `0x4000_0004` | STATUS | RO | CNN 输入；`[0]` busy、`[1]` done、`[2]` error |
| `0x4000_0008` | INPUT_ADDR | RW | 输出给 CNN |
| `0x4000_000C` | OUTPUT_ADDR | RW | 输出给 CNN |
| `0x4000_0010` | WEIGHT_ADDR | RW | 输出给 CNN |
| `0x4000_0014` | BIAS_ADDR | RW | 输出给 CNN |
| `0x4000_0018` | IMAGE_SIZE | RW | 输出给 CNN |
| `0x4000_001C` | CHANNELS | RW | 输出给 CNN |
| `0x4000_0020` | CNN_PARAM | RW | 输出给 CNN |

## 7. 验证结果

### 7.1 新增 B1 存储子系统

执行：

```powershell
python scripts\run_partner_datapath_b1_tests.py
```

结果：

```text
PASS checks=30
face_soc_cpu_memory_top 编译并成功展开
证据目录：build/runs/20260929_164949_997532_partner_datapath_b1/
```

已覆盖 A 口整字和 byte strobe、IO B 口读写、CNN 优先级、读返回 owner、A/B 冲突、非对齐错误、MMIO 读写、STATUS 只读和 CONTROL 自动清零。

### 7.2 正式 Control + 生产 Datapath 回归

执行：

```powershell
python scripts\run_real_datapath_review.py --datapath-root partners\datapath\delivery
```

结果：

```text
ADD PASS: x1=1, x2=2, x6=3
MIXED PASS: cycles=117, stalls=1, redirects=10,
            dmem_reads=17, dmem_writes=10,
            mmio_reads=1, mmio_writes=1
证据目录：build/runs/20260929_164617_016549_real_datapath_review/
```

测试前后对生产 Control 和 Datapath 源文件计算 SHA-256，结果完全相同。

## 8. 尚未声称完成的内容

以下内容不在本次 Datapath 回传包中，不能据此宣称整机 FPGA 已完成：

- `image_io_bridge` 的 UART、摄像头或其他板级物理引脚协议。
- 真实 CNN accelerator 的 DMA、计算核和 STATUS 产生逻辑。
- 目标 FPGA 厂商 RAM/ROM primitive、约束文件、时钟约束和 bitstream。
- 三方对真实 CNN、真实图像流和板上 BRAM 的联合验收。
- 公共兼容 package 新文件哈希的三方共同归档；Control C1 的端口、编码和 RTL 本身未改变。

此前提出的“CPU 合并成五到六个大模块”是教学和展示层的模块划分方案。本次没有重写生产 Control/Datapath 的内部文件结构，因为那会跨越双方所有权并放大回归风险；当前新增顶层已经能按该逻辑分组展示，但底层 RTL 保持负责人原交付结构。

## 9. 负责人建议检查项

请 Datapath 负责人重点确认：

1. `data_sram_tdp` 的一周期读时序是否满足目标 FPGA BRAM 推断规则。
2. A/B 同字冲突采用“A 优先、B 完成并报错”的规则是否接受。
3. CNN 固定高优先级是否继续作为 v1.0 仲裁策略。
4. `CONTROL[1:0]` 单周期脉冲和 STATUS 位定义是否与 CNN 负责人一致。
5. 最终工程是否使用 FPGA 厂商 IP 替换行为级 RAM；若替换，外部接口和时序不得改变。

## 10. 回传打包方法

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_datapath_delivery.ps1
```

脚本会：

1. 校验原始 43 个文件未丢失、未改动；
2. 只打包 `partners/datapath/delivery`，不会把只读基线或 CPU Control 私有目录放进回传包；
3. 在包内生成 `docs/datapath_delivery_sha256.txt`；
4. 在 `build/deliveries/` 生成带时间戳的 ZIP，不覆盖旧包。
