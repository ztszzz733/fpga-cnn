## 2026-10-24 发布到 moon：本轮用户明确授权

用户最新要求提供更新说明.md并将修改后的项目上传origin/moon。根目录更新说明.md为本次发布入口。保留moon原有连续帧/FX8/NEureka历史源码与记录，合入当前自研CNN、DDR/cache、CPU/PS固件、测试和交付文档；不能强推覆盖远端历史。下方“没有提交推送”等语句是此前实施阶段记录，不是当前禁止上传的限制。发布范围仍为代码与既有离线证据，不新增上板、整机综合或长全网仿真。验证原始源码hash包含既有CPU文件的工作区CRLF字节；新受测文件/证据由.gitattributes保留字节，不能因旧Git换行差异篡改历史记录。

## 2026-10-24 DDR/cache与新CNN已实施：用户限定本轮先改代码、不上板

用户授权按刚才七页图严格连线并更新旧CNN，随后明确“不需要上板，你先改我代码就行”，并继续。新代码入口rtl/soc/ees331/face_soc_ees331_top.sv、rtl/filelists/system_ees331.f，六个平级PL实例+PS7；不再引用旧FPGA1 CNN。原face_soc_top/system_cnn保留历史入口，勿混编。128根图示信号由scripts/check_ees331_wiring.py核对名称/位宽/两端连接PASS；PS wrapper107导出端口核对真实VivadoBD通过。CPU Control/Datapath/bai原文件未改。详见docs/ees331_code_integration.md。

实现：cnn_ees331零等待MMIO；fixed_schedule_compact一份640×256模板20KiB、四PC、16owner+最多2消费者槽，无展开任务/消费者大表；2K3/4K1/DW7/Post/Add/Pad各1；非法owner/占用冲突报6并cleanup。新Post/DW7同步存储变体保留旧算术文件；DW7多1取权重拍，部分Post参数映射LUTRAM。datasram_ddr_subsystem分离CPU16KiB固定一拍RAM与128KiB/64Bline/2way/4bank cache，首版全局一笔请求在途，非4MSHR/多bank同拍命中。AXI3HP0数据64、ID6、8beat64B；逻辑16MiB加物理0x10000000；WBWA、区域clean/invalidate维护排队、模型保护、cancel排空。bridge GP0 AXI3数据32/ID12仅邮箱，CPU经索引数据控制CNN/cache，frame/epoch ACK。IMEM8KiB、新服务程序437RV32I/1748B。PS UART1/J3 server与host脚本已写；PS main未编ARM BSP/ELF，链接必须避开共享32MiB。未知CPU响应或cache维护超时后PSserver锁住后续写；热启动先CPU状态检查，自检用第二窗口0x11000000。RESET仅idle，不等于运行中abort；AXI不响应不能软件当已排空，故障恢复需整机复位。

最新真实六模块gate build/runs/20261024_215712_328991_ees331_soc PASS，源hash未变：实际CPU/ROM/bridge/新CNN/cache+AXI PS/DDR模型，4张8×8 RGB ROI/每图8步/32任务/71856检查字节/4份1024B从DDR fence后读回。921718拍含CPU配置，跨图work146625/MAC144009拍，峰值4活跃帧；4096B SHA eecab63788e81b2076db269cf649de919bfdfec17c9a5f3d5ed2e5ab2ac6be32。内核cache四模式最终215719_084012_ees331_full PASS full_network=false：overlap864284、serial1736040、preloaded855818、stress909564；约2.01倍小图吞吐，非全网/板速。定向compact215557_216919、cache184132_914735(826项)、operators183642_006922、control184020_033055、PSserver220057_896748均PASS。完整131步四112×112上传包只准备校验，未跑DDR全网；历史653428459拍/512B哈希不能套用DDR版。不自动启动长全网、上板或继续硬件工程。

仅独立OOC资源已过：cache+CPU RAM1785LUT2489FF37BRAM36eq0DSP；DW7 6757LUT4075FF8BRAMeq12DSP；独立Post3402LUT346FF1.5BRAMeq22DSP+LUTRAM。没有本轮整机资源/时序通过。PS BD生成成功D:/zhang/ees331_build/20261024_183937_108118_ees331_ps，参数手册1GB/32bit/533MHz、FCLK50MHz、MIO48/49，默认PCBdelay非实板验证。D:/ees331_ready只读核对，实际是旧JTAG-AXI PL工程无PS7/DDR配置，未混入新CNN。整机项目尝试遇到括号路径/loaderPATH，runner已改ASCII源快照和binPATH，用户限定代码后未继续综合/布线/bitstream。没有上板/下载/Git提交推送；历史6b28122推送仍是上一轮。

## 2026-10-24 DDR加入六模块的draw.io接线方案

用户要求原六模块同层级IO接线图，地址/数据/控制分组标名称与位宽。新增deliverables/ees331_ddr_io/ees331_soc_ddr_io.drawio（7原生可编辑页），改前/改后总图、地址、数据、本地控制、AXI3 GP0/HP0控制、DDR/J3/时钟页；同源SVG/PNG、README、io_connections.csv/io_manifest.json及图形校验。生成器scripts/draw_ees331_ddr_io.py。为保留六功能位置，方案明确将第五image_bridge位置改成拟image_control_bridge（GP协议转换+PS/CPU邮箱+CPU零等待MMIO译码转接）；PL UART收图移PS程序，CPU MMIO经第五模块转接到新CNN；datasram包含CPU本地固定一拍RAM及CNN cache，新增HP0到PS。新CNN MMIO封装/紧凑调度/cache CSR均拟实现接口，不要当现有RTL。旧页严格使用生产单路mem_*，旧cnn_mem_fault只参与顶层LED，不接旧CNN。PS端口名称/静态位宽核对本机Vivado2026.1 PS7 component.xml，HP0拟配64bit，GP0为32bit；DDR32DQ/4DQS/4DM/15Addr/3BA。仅绘图，未修改RTL/仿真/上板/推送。

## 2026-10-24 cache/IMEM容量补充：仍仅分析

用户询问现有资源可做多大cache及64KiB IMEM是否过大。核对建议先128KiB、压缩调度后以256KiB为目标；按32bit组织分别用32/64个BRAM36，板上共140块。现有2K3/4K1独立综合合计22块，512KiB cache的128块+22已超140，384KiB仅余22块供所有其余模块，不建议。未做新整机综合不能称已fit。IMEM已有autoload demo98指令392B、overlap67指令268B；两份program.mem均NOP补齐4KiB。历史hybrid CPU映像最大4180B。建议新固件先预算8KiB，超出再16KiB；64→8KiB按32bit组织释放14 BRAM36（56KiB有效数据）。全网仿真由C++驱动，没有对应新CPU固件，不要将demo长度当最终程序承诺。详见docs/ees331_ddr3_cache_pc_input_plan.md第11节；第5节预算改IMEM8KiB后128cache逻辑总量316KiB，256时444KiB，均需物理映射验收。仍未修改RTL/推送。

## 2026-10-23 最新板卡信息与DDR方案：仅规划，尚未实施

用户提供 `D:/参考文献EES331_UserManual_v1.0_1220.pdf` 并要求基于当前项目给出“DDR3保存图像、SRAM作cache、电脑一根数据线输入”的改动方案。手册确认EES331为xc7z020clg484-1，1GB DDR3挂PS；这覆盖此前“只有512 KB且无DDR”的硬件前提。J3为板载调试+PS UART1并支持供电，J8上口为PL CP2103串口、下口为PS UART0，J4为独立PS USB2 OTG。已完成本地方案 `docs/ees331_ddr3_cache_pc_input_plan.md`：建议PS裸机经J3收图写DDR、PL经HP0/128KiB cache访问，保留自研CPU本地存储/邮箱及2K3/4K1，压缩固定调度表，分阶段四图全网与上板验收；J4 Bulk为后续路线。以上均为拟定设计/容量预算，未改RTL、未重跑仿真、未上板、未提交或推送本次文档。历史代码上传已于提交6b281225047fbcd74553b79d86fbf8c1158d3a92成功推送origin/zhang；不要把先前上传请求当本轮实施授权。

## 2026-10-23 当前交付：算子数量优化、同一四图全网重跑 PASS

后续约束：用户确认只有512 KB存储、没有DDR/Flash等其他存储。目前只完成容量分析与方案讨论，未实施512 KiB适配、模型裁剪、INT4或跨层分块。当前新CNN主数组声明合计17,128,048 B（16 MiB共享SRAM + 350,832 B内部缓存/表/运行命令），约16.335 MiB，另少量状态寄存器；不能当作板上已有容量。原INT8权重980,096 B已超512 KiB。旧face_soc_top仍接旧CNN，默认256 KiB数据SRAM+64 KiB指令ROM。用户随后明确要求将当前已修改项目代码提交并推送到origin/zhang；上传包含源码、复现说明和验证资料，不代表512 KiB或上板已完成。

用户授权优化算子数量并重跑相同完整仿真。最终选择K3×2/K1×4，其余DW7/Post/Add/Pad各1，总10单元；算术与控制RTL、bai SRAM、四图片/权重/参数/输入pace80/16MiB容量均未改。runner新增--k3/--k1/--post，配置同时传Verilator参数和C++宏并写入缓存签名/metrics；候选缓存.self_full_native/k3_2_k1_4_post_1，旧基线未覆盖。RTL及runner默认仍为历史4/2，必须显式--k3 2 --k1 4 --post 1选择本次2/4，实际硬件集成例化K3_UNITS=2/K1_UNITS=4/POST_UNITS=1。

完整run build/runs/20261023_194836_645744_self_full 已于20:12:24 PASS，exec session36186退出0，无活动仿真/定时任务。匹配gate194655四项PASS：overlap404271、serial1195599、preloaded400367、stress543978。完整重跑653428459拍，计算完成653428352拍；相对基线180539的1138093351拍减少484664892拍（42.5856887%），同频批次吞吐1.741726倍（+74.1726%）。按假设100MHz四图11.38093351→6.53428459秒，不是已验证板级频率。主机计算1421.11秒、总1428.251秒，不当作硬件加速。

两轮各524任务/分配/释放、935241728 MAC、77349168检查字节、4份128UINT8外部读出全部PASS；512字节输出逐值等于基线与整数golden，SHA80351fb04be5c55bc45d6e6fcadaef6680b20d0532d15f7bb5bf5c661416a44f。真实跨图工作82088133→315946899拍（批次占比7.21%→48.35%）；1×1同类资源排队2016986427→0帧·拍，K1平均busy97.807%→85.253%，K3平均busy4.514%→15.668%；K1仲裁等待只占active0.217%，不等于包含正常响应的全部访存成本。四帧每帧至多一当前job，继续加K1数量不能供给更多并行任务。

交付deliverables/self_cnn_full_optimized/README.md、docs/self_cnn_full_optimized.md；真实前后同轴流水/周期/池占用/两MAC窗口共5PNG已目视检查；2个GTKWave会话实际PASS各10唯一物理信号，architecture.drawio保留16MiB仿真容量。scripts/compare_self_full.py仅接受已完整PASS/同manifest与数据hash/固定配置4/2→2/4/受保护RTLhash相同的对照，保存原始证据、输出、表格、资源来源与provenance，原self_cnn_full_frames交付未覆盖。复现full：run_self_full.py --reuse --k3 2 --k1 4 --post 1 --full --data build/self_full_data --gate build/runs/20261023_194655_786340_self_full --modes overlap。

修改前16源码hash快照在build/self_full_baseline_source。C++仅配置宏/launch-kind断言/metrics pool变化，bootstrap支持cpp_defines；未改时序driver/算术checker。旧单核OOC相加仅六卷积核LUT11654→11680（+26）、FF9002→8974、BRAM36等效29→22、输入/权重局部缓存78→54KiB、DSP0。没有新的整机综合/布局布线，旧Post/DW7存储推断障碍及16MiB仿真容量边界仍存在；不能宣称整机面积或上板通过。调度估算在build/self_full_pool_review，最终收益以上述实际RTL数据为准。

## 2026-10-23 当前交付：四张完整测试图 MobileFaceNet 真RTL全网 PASS

用户明确授权完整神经网络多图仿真并在完成后分析性能，选择四张不同112×112完整测试图。此授权覆盖历史暂停/不要全网范围。完整run build/runs/20261023_180539_292440_self_full 已于18:49:29完成PASS，无活动仿真或定时任务；不要把旧RUNNING历史当仍在执行。

真实新入口 tb/self_full_sim_top.sv + tb/integration/self_full_main.cpp，实际self_fixed_network_top、K3×4/K1×2/DW7/Post/Add/Pad各1、bai四bankSRAM，MAX_TASKS1024，模板容量256，SRAM仿真16MiB。CNN收到一份131步模板和4图片地址，内部展开524任务。全部51Conv/12Add/32Clip/2Relu覆盖；末尾Reshape无算术，原模型无L2归一化。预训练checkpoint SHA780e31e7c2639a0d5fdebe843f5df3ff81fda79a090164df0ff40514d172853a，来源/导出/4输入图见build/self_full_model。数据build/self_full_data初值12608512字节，中间和输入初值A5，gold只作checker。

最终完整overlap：1138093351拍、计算完成1138093244拍、524任务/分配/释放、77349168检查字节、935241728MAC、4份128UINT8真实IO读出。输出512字节SHA80351fb04be5c55bc45d6e6fcadaef6680b20d0532d15f7bb5bf5c661416a44f。主机计算2620.83秒，含初始化/收尾总2629.997秒。每次RTL写请求字节比较独立整数参考、实际读响应与shadow核对、最终输出及只读/尾保护真实SRAM回读；不是每个中间张量另作全量读回。

性能：1×1占93.42%MAC，两实例平均busy97.807%，K3各约4.51%、Post6.08%。1×1内部MAC_READ/MAC_ACC每两拍一MAC，其累计active分解为78.49%MAC两拍流程、20.62%逐字节读、0.76%写、0.128%仲裁等待。主要优化方向是1×1MAC流水/并行度和宽读/缓存，不应按旧小图继续盲加K3/Post。仅完整overlap实测，无全网serial加速比。100MHz条件换算11.38093秒/四图、0.3515图/秒，不是已达成板级频率。四图跨图实际工作82088133拍、跨类24732963拍、峰值4图在途，输入全部提交3048416拍。

运行器scripts/run_self_full.py，生成器gen_self_full.py，恢复restore_self_full_model.py，报告prepare_self_full.py。项目内Windows Verilator/MSVC使用第三方wheel5.48.0配套runtime5.49dev，来源hash已存.tools/verilator-native/SOURCE.json；真实卷积单测与历史XSim输出/所有周期一致。--output-split-cfuncs500仅主机提速约5.6x，硬件计数不变。匹配小gate180351四项PASS(overlap474575/serial1195599/preloaded470543/stress619789)，不可当full性能。

交付deliverables/self_cnn_full_frames/README.md、docs/self_cnn_full_frames.md，输入/流水/全步骤/算子占用/两个真实MAC窗口PNG、512字节输出与量化/反量化CSV、原始events/metrics/result/来源hash、architecture.drawio。两个GTKWave会话实际验证PASS，每个10物理信号无重复；波形只记录相对起点256拍窗口，未存全局起始拍；全程任务时序用真实events。独立源码/数据/输出hash、事件依赖、量化覆盖均复核通过。

边界：16MiB为仿真容量，不是Z7020片内存储已适配；未产生新的完整LUT/FF/BRAM/DSP/时序报告，旧Post/DW7综合问题仍在。输入为合成数值图；全图固定首图诊断量化尺度，FP32余弦0.9760～0.9897不代表识别精度。不是CPU/UART集成、无限连续帧或层内条带流水。

## 2026-10-23 当前交付：地址驱动固定流程、bai SRAM、四图流水

用户进一步授权接 bai 分支 SRAM、增加瓶颈算子、四图依次输入，并明确目标为 CNN 得到图片地址后自主按固定 MobileFaceNet 流程并行/流水；可先不跑全网。实际分支为 `bai-datasram`，原样导入 `rtl/overlap/datasram_banked.sv`（commit `0f7cc8d35e21e5e6458da15797512e9e6a4eddbd`）到 `rtl/cnn_stream/bai/`，来源 SHA 在 SOURCE.json。未 merge/切换旧工作分支。

新入口 `rtl/cnn_stream/self_fixed_network_top.sv`、filelist `rtl/filelists/cnn_self_stream.f`。外部只写单图模板和 1～4 个输入/工作区/帧号地址描述，CNN 内部 `stream_fixed_programmer` 展开前驱/owner/消费者，`stream_dispatch` 按输入就绪及依赖轮转分配。默认 K3×4、K1×2，原 DW7/Post/Add/Pad 各1，共10实例。真实四bank256KiB SRAM，CPU A 与 CNN/图像 IO B 仲裁；图像写完后 frame_valid/ready 提交，结果必须真实读完后 result_ready。有限批次，默认16模板步骤/64总任务、16工作槽；非完整网络导出、非层内逐行流水、非CPU固件或UART集成。

最终7项真实算术/协议回归 `build/runs/20261023_162331_369628_self_stream` PASS：overlap83201拍，serial276229（3.320×批次吞吐），CPU同字碰撞+慢读204480，clear重启83201，SRAM fault全局复位恢复83201，禁用K3#0为101153，预存图片80077。每项44任务/28812检查字节/44分配44释放/4结果；输出32字节SHA `d961e0eb6f303e1f4e49a9792e92778ba2d4f5b4ee6600976d3417ee6f9d08f0`。四张不同合成7×7 RGB，诊断权重，单图11步，非完整MobileFaceNet。真实跨图工作19642拍、跨类工作4604拍、双以上K3 MAC14528拍，峰值3套同拍MAC；4图在途不能当4套每拍全算。

最终九组算子扫描 `20261023_162421_993076_self_stream` PASS：K3/K1/Post为2/1/1时131777，3/1/1=101109，4/1/1=100493，3/2/1=101153，3/1/2=100537，3/2/2=100317，4/2/1=83201，4/1/2=100493，4/2/2=83201。扫描复用最大实例池、禁用多余单元；候选另编实际10实例同样83201。独立 `20261023_161153_843242_stream_programmer` 覆盖1～4图地址展开、反压、4类非法配置PASS。旧空VCD调试运行不作波形证据；最终25物理信号，4个GTKWave会话实际验证PASS。

交付 `deliverables/self_cnn_four_frames/README.md`、4张PNG、原始CSV/VCD、GTKWave启动器、架构drawio；接口 `docs/self_cnn_four_frames.md`。复现 scripts/run_self_stream.py / test_stream_programmer.py / prepare_self_stream.py。旧双图交付不变。无活动仿真/定时任务。旧 Post/DW7 RAM 推断综合障碍尚未修复，不宣称完整资源/时序或上板通过，不自动恢复历史全网长仿真。

## 2026-10-23 前一阶段：自研卷积、3×3两套、其余各一套

本次用户明确授权从GitHub的zhang分支实施，覆盖下方历史“仅文档/暂停”。随后强调已有多数算子，主要替换neureka大卷积。新隔离入口`rtl/cnn_self/self_network_top.sv`及`rtl/filelists/cnn_self.f`：自研K3×2（普通/DW3共享池）、K1×1，原DW7×1、Post×1、独立Add×1、Pad×1。旧算子算术源码、旧入口、CPU/生产存储不改；新入口无NEureka运行依赖。调度/租约/结果协议源于旧设计，任务表默认缩小为64，8槽。

最终双图小数据回归`build/runs/20261023_150822_041360_self_pair`十项PASS：两张不同合成7×7 RGB图、诊断权重、22任务、每项14,406字节检查、22分配/22释放、两份8字节结果（不是128维特征）。正常92,286拍，双K3真实MAC同拍2,220，跨类有效推进544拍；只启用任一K3均129,204拍。慢读/反压/限速/clear/内存故障/非法opcode、依赖、结果配置恢复均PASS。最终SHA`c0010b6a6701a08cc613fa59c293971a623d6e33996d5cea9f07fc2dadc96520`。旧150248回归使用较早TB仲裁采样，最终已修正边沿竞态并重跑；不要用旧计数替换最新。

独立卷积`20261023_145746_335613_self_conv_unit`14数值/18非法配置PASS，参数补充审查`20261023_150855_372167_self_conv_parameter_review`52数值/6204字节PASS。完整七实例综合`20261023_150436_706083_self_cnn_synth`FAIL：原Post参数RAM无法推断（Synth8-3391），旧DW7和新复制命令表也有寄存器展开警告。单K3独立综合通过不等于整体资源或上板通过。不要自动继续旧全网长仿真。没有活动定时任务。

交付`deliverables/self_cnn_pair/README.md`及`verification_report.md`，接口`docs/self_cnn_interface.md`。复现`python scripts/test_self_conv.py`、`python scripts/run_self_pair.py`，已有Vivado XSim，无WSL依赖。本机历史模型/人脸路径不在本次克隆中；完整图导出、全网数值、流式输入、连续帧及生产接口仍待后续。新算子缓存同步读取，无整块复位；原其他算子资源组织未重写。源/数据/结果哈希见新报告。

## 2026-10-23 自研卷积替换需求交接：仅文档（历史范围）

用户因板子资源不足决定后续用自写卷积替换NEureka，借鉴其数据复用，所有卷积和其他独立算子模块各两份，目标是两张图片的真实算术与自动分配并行验证。随后用户明确收窄为“你不用写代码，只写文档”，并要求给另一个agent交接。需求与历史证据、阅读地图、资源边界、接口、分阶段验收见 `docs/CNN自研双算子完成需求_v1.md`。本次仅更新文档；新替换方案未实现/未验证。不要因读到需求就启动开发、编译、仿真或定时检查，等待新的实施指令。MAC数量/缓存大小/通用卷积合并方案未定稿，不得当成用户已批准规格。旧两图全网仍为重启中断，不恢复旧NEureka长仿真。

## 2026-10-23 用户重启后暂停（覆盖下方运行记录）

用户明确告知仿真已停止、电脑已重启，要求先不要继续。不得启动仿真、编译或恢复定时检查，等待用户重新授权。mobilefacenet定时检查已删除。build/runs/20261023_000710_network_pair原RUNNING为重启残留，已标记INTERRUPTED_BY_REBOOT；末日志仅DONE 4/746，最后完成日志wall=1382.51秒，不等于实际总运行耗时，未取得完整PASS。代码、编译缓存和全部已有记录保留。没有运行时断点，恢复时可核对复用编译缓存，但本次完整仿真需从头执行；不自动重跑。

## 2026-10-23 两图真实数值仿真已启动（最高优先）

用户“继续下一步”，小数据地址重排实际RTL回归已PASS后，已通知用户并启动两张完整人脸长仿真。唯一活动run build/runs/20261023_000710_network_pair，会话20832；run_network_pair.py --data build/mobilefacenet_pair_plan --reuse --full --gate build/runs/20261023_000414_network_pair。复用同一个已验证程序compile=0，初始补边DONE 1/746(192990周期/0.591秒)仅代表首命令，不能称全网PASS。不重复启动/不编译。自动检查mobilefacenet ACTIVE每30分钟，正常安静、完成或错误通知；先读run/result.json和fast_reader/sim.log尾部，用户要求停时停进程及检查。

新增通用tb/integration/network_pair_main.cpp，读取results.bin的帧号/地址/字节数、任意命令数<=1024，从lease推导分配数、按帧号保存外部结果；无6帧/10命令/1024字节硬编码。不读golden.bin进SRAM，完成逐命令expected.bin检查、释放覆写0xD7、外部读取确认、槽尾64字节写保护、每完成一命令sim.log记录周期和wall。scripts/run_network_pair.py对full设小回归同源码/库哈希门槛，full只跑fast_reader，timeout86400不是预计耗时；缓存.network_pair_build。完整输入两不同112×112图，746命令、262分配释放、两份128字节输出，SRAM预加载无CPU/UART、非条带流水。池5.36MiB/实验地址空间7.99MiB，量化共用单图诊断尺度，不宣称识别准确率。

小回归build/runs/20261023_000414_network_pair两项PASS：26命令、48884检查字节，20分配/20释放，各2份90字节补边最终输出(不是人脸embedding)；前三层真实ROI+独立Add/DW7/pad探针，所有算子均真实RTL。fast周期156356、slow298832，分配6/6/10/2/2与4/8/10/2/2，双busy40572/46426，输出SHA7414a93ff2b26895e5d9ad1e830da396752aec5cefb2d84e2257a7843b160201。编译40.815秒、仿真28.183/47.942秒，总117.914秒。新gen_pair_relocation_small调用通用化plan_full_buffered(small=True)；plan_full默认完整373/帧约束不变，未覆盖现有full数据。小数据build/pair_relocation_small/plan、池23552字节。deliverables/network_pair_small两PNG已视检，GTKWave各16信号PASS。

全网PASS后运行Windows Python scripts/prepare_network_pair.py run目录，交付deliverables/network_pair_full；核对源码数据和outputs SHA、256字节输出，视检两PNG，GTKWave隐藏窗口verify_*.tcl各16信号(必要时沙盒外避免DLL错误)。报告timing_seconds和cycles/100000毫秒@100MHz，更新说明及AGENTS，交付后暂停mobilefacenet。若报错先查直接原因并保留run，不能盲目重跑长仿真。当前仍在运行，不要把小回归或控制模型PASS当完整两图成功。

## 2026-10-22 两张完整人脸的缓存计划已完成（最新）

用户最终选择两张图可同时就绪，继续两图方案。当前仅完成完整计划和快速控制测试，没有启动长时间完整两图数值仿真、没有活动会话/自动检查。新数据build/mobilefacenet_face2_fixed来自person_2，冻结第一图逐层诊断尺度；第一图源build/mobilefacenet_full_data保持不变。gen_mobilefacenet_full.generate增加可选output_scales，CLI --scales-from；并非识别准确率校准。

新scripts/plan_full_buffered.py从真实读写地址推导张量生命周期/通道分组写者/Add双输入，压缩只读跨度、保留64字节对齐及槽尾保护。build/mobilefacenet_pair_plan为两张不同图片共746命令、262中间张量，frame-interleaved，每帧内部顺序。8槽，实际每帧峰值3槽(第四槽64字节占位)，池5620224字节约5.36MiB，readonly2752512，总8372736字节约7.99MiB；不复用逻辑中间负载38674584字节。权重尚复制两份，未最优容量/未条带化，生产SRAM未改。results.bin每命令16字节flag/frame/addr/bytes，最终节点744/745，各128字节；不可使用旧network_output_main.cpp的六帧/10命令/1024字节硬编码直接跑。

validate_buffer_plan扩展DW7/Pad，静态PASS。tb_full_buffer_plan + run_full_buffer_plan.py真实dispatch/lease/result控制RTL，算子仅延迟模型；部分执行clear重启后746完成、262分配262释放、两结果读取确认、双核分配292/292，post126/DW7 2/pad34，PASS。编译8.638秒/仿真0.269秒/总8.908秒，control_result.json+control_sim.log。缓存.network_output_build/full_plan_test。不能把此称完整网络算术PASS或推断真实硬件速度。旧第一张顺序入口数值PASS仍是历史证据；第二张仅软件参考。

交付docs/mobilefacenet_pair_plan.md及deliverables/mobilefacenet_pair_plan。下一步通用数值测试入口读取此计划，先小数据地址重排回归，再安排完整两图真实算子长仿真；仍不要无提示自动开始大图。当前无活动仿真。

## 2026-10-22 最终结果读取确认已通过（最新）

新增隔离quant_network_output/network_result_handoff，输出预约即保留、写响应排空后发布帧号/地址/长度，result_ready=外部全部读取完成，握手后才能回收。compute_done=计算结束，done还需全部结果取走及槽释放；反压描述稳定，单描述轮转可乱序。result_error成功为0，故障走全局cancel；clear/cancel须系统取消旧读写和迟到确认，没有跨复位token。network_buffer_leases新增external_hold，旧顶层和TB接0、旧协议回归PASS。

build/runs/20261022_230142_network_output两项fast_reader/slow_reader PASS，无活动仿真/自动检查。六帧小ROI前三层+人工残差60命令，136704字节检查，外部读取6144字节，输出SHA均8608f090b4ea85fbeb62ab79219cb89f9387ff27a4a922d8128f5d608627b998。周期298121/683846，42分配42释放；慢读每描述等待90000拍后每7拍读4字节，同时算子访存反压；等待外部期间39条其他命令完成、wait_buffer7129拍；compute_done556081拍。编译41.567秒，仿真83.896/127.938秒，总254.538秒。复用真实NEureka库，仅编新包装，缓存.network_output_build。独立result_handoff_test早ready/乱序完成/双待取/保持/clear/cancel/错误配置PASS(编译8.358秒/仿真0.021秒)，旧lease回归PASS(6.802/0.013秒)。

deliverables/network_output两PNG已视检，GTKWave两会话各16信号PASS；沙盒内GTKWave DLL重定位错误，沙盒外隐藏窗口成功，不需重装。docs/network_output_handoff.md接口文档；run_network_output.py --data build/network_buffered_data，后续--reuse校验哈希；prepare_network_output.py制作交付。外部读取为TB直接访问SRAM，非生产总线带宽测试；未接CPU/UART，不是全网多图。下一步完整网络生命周期规划和小验证，再全网多算子入口。不要自动跑大图。当前用户授权的输出交接已完成。

## 2026-10-22 缓冲区复用已通过（覆盖下面的进行中记录）

最新build/runs/20261022_222606_network_buffered完整PASS，无活动仿真。六帧小ROI前三层+人工残差Add，60命令，每项136704检查字节，42分配/42释放，全部槽反复复用且释放后立即0xD7覆写，4场景输出SHA均8608f090b4ea85fbeb62ab79219cb89f9387ff27a4a922d8128f5d608627b998。双核/单核/限速/重启周期297264/364824/432601/338020，分配21/15、0/36、13/23、21/15；wait_buffer2/2/0/2，peak_live5。当前compile0，单核78.799秒、限速134.896秒、重启105.673秒，总321.640秒；双核从221716哈希验证复用（原165.651秒，原编译13.891秒）。旧221716单核240秒超时、221525越界、221452漏编译模块均保留，不能把当前总耗时当全部调试耗时。独立lease协议测试PASS（8.315秒编译/0.020秒仿真），plan离线检查PASS。交付deliverables/network_buffered，两PNG目视检查、GTKWave各14信号PASS，设计docs/network_buffered_design.md。原型为静态物理8槽+硬件运行时预约/代号/消费者完成释放，中间池39424字节（38.5KiB含尾保护）vs六帧不复用逻辑张量136704字节；不含只读输入/权重/命令、控制掩码表或输出持久存储，不宣称完整网络容量。最终结果由TB释放前捕获，生产外部输出握手仍待接入。下一步完整网络生命周期/输入条带/外部输出握手，勿自动跑大图。

## 2026-10-22 缓冲区复用进行中（继续时先读此处）

新增隔离network_dispatch_buffered/network_buffer_leases/quant_network_buffered，静态8物理槽+运行时占用/代号/消费者掩码，NEureka库复用。6帧（两不同人脸交替）真实ROI前三层+人工残差压力Add，60任务，42lease；不是全网。中间池39424字节含每槽64字节宽读取尾保护，只读输入/权重/命令不计。最新唯一运行build/runs/20261022_222606_network_buffered，会话71518，--reuse --reuse-passed 20261022_221716_network_buffered，双核旧PASS已按源/数据哈希复用，单核新PASS，限速/重启还在运行；不要重复启动。221716单核因240秒电脑超时停止，无数值失败；新版上限900秒。旧221452为编译列表漏模块，221525为尾部宽读越界已修。protocol build/buffer_leases_test/result.json PASS；plan_validation也PASS。待全部PASS运行scripts/prepare_network_buffered.py 活动目录，视检两PNG、GTKWave各14信号、更新结果文档/AGENTS后交付。不能将仍在运行说成四项通过；不启动大图或自动检查。设计docs/network_buffered_design.md，最终外部输出消费握手仍待接入，当前TB回收前捕获结果。新增生成器自动计划校验不会影响运行中数据；勿重新生成活动数据目录。

## 2026-10-22 两图完整命令调度入口：小数据验证通过

新增隔离network_dispatch/quant_network_parallel，1024条16字命令、最多两个早于本节点的前驱、每拍扫描一节点、双NEureka空闲轮换分配、一post/Add、一DW7(MAX_WIDTH=7)、一pad；23客户端。未替换旧residual/三槽release路径，当前每帧严格串行、跨帧重叠、保留全部中间数据。小数据20261022_215648_network_parallel四项dual/only_engine1/skew_stall/restart全部PASS：26命令、48,884字节，最终SHA 6ff442383686774c722775270e29240a91a28422b44a46fb9e8ac543c4a3d1bb。两张不同人脸ROI前三层+独立Add/DW7真实512通道特征/补边探针，不能称完整两图数值通过。周期156332/185010/192767/196988，正常分配6/6、限速4/8；正常双busy40572/卷积post busy8207（含访存等待）。主编译14.770秒，四仿真176.725秒，总192.885秒；复用哈希匹配.neureka_full_hier_build真实NEureka DPI库，两实例独立，不替算。新缓存.network_parallel_build。完整746条命令计划在build/network_parallel_data/full_plan，复制同一全图两份；dispatch_result PASS仅算子延迟模型调度，非算术验证。两输入汇合/清除重启/自依赖拒绝/fault取消PASS。交付deliverables/network_parallel，两图GTKWave15信号通过，设计docs/network_parallel_design.md。无活动仿真，无定时检查。下一步中间存储生命周期和容量，再全网两图数值/条带；不要盲目启动大图。

## 2026-10-22 完整单图网络已通过（覆盖以下活动运行记录）

20261022_201457_mobilefacenet_full 已PASS，无活动仿真。完整112×112 RGB经51卷积+12Add、373命令产生128维量化向量，与整数参考逐字节一致；检查19,337,292字节，34,835,459周期，100MHz对应348.35459ms。本次compile=0，simulation=5076.796秒，total=5078.458秒。prepare核对全部源码/头文件/数据/输出哈希。交付deliverables/mobilefacenet_full，三PNG及GTKWave视图每个10信号均验证PASS；done在最后采样点升高，以边界标注，不伪造延时。完整顺序入口通过不等于双NEureka全网并行、UART或识别准确率通过，仍用约20MiB实验内存和单图诊断量化。自动检查任务完成后删除，不再轮询。

## 2026-10-22 20:15 用户恢复（覆盖以下暂停及旧运行记录）

用户明确说继续，已复用编译缓存并启动唯一活动仿真 build/runs/20261022_201457_mobilefacenet_full，会话51466。源码哈希匹配，compile=0，首补边DONE 1/373，尚未全网PASS。运行超时上限86400秒不是预计耗时。每30分钟自动检查 neureka 已更新为本目录并恢复ACTIVE，不频繁轮询，不重复启动。完成或报错按自动检查提示处理；若用户再次停止须立即停止并暂停检查。旧184024仍为STOPPED_BY_USER，不能当作完成。

## 2026-10-22 用户暂停（优先于以下运行记录）

用户明确要求先停止，目前无时间继续跑。已停止 build/runs/20261022_184024_mobilefacenet_full 仿真并确认进程退出，result.json 标记 STOPPED_BY_USER；本次仿真耗时 673.967 秒，未取得全网络 PASS。代码、编译缓存和日志均保留；以后源码未变可复用编译程序，但未保存运行时断点，计算需从头开始。定时检查 neureka 保持 PAUSED。用户明确恢复前，不重启仿真、编译或自动检查。

# 项目网络代理

- 用户所说的网络连接是 Codex 网络代理，不是虚拟机 SSH 或开发板。
- 已确认代理为 Clash Verge / Mihomo：`http://127.0.0.1:7897`。Windows 系统代理已经启用。
- 代理参数保存在 `network/proxy.psd1`；`.codex/config.toml` 为本项目的 Codex 命令环境设置相同的代理变量。
- 后续任务直接复用此配置。不要在每次对话开始时重新扫描端口、检查代理或重新配置系统网络；仅在实际网络请求失败或用户要求排查时诊断。
- 当前会话未加载新配置且确实需要联网命令时，在同一次 PowerShell 调用中先用 `Import-PowerShellDataFile .\network\proxy.psd1` 读取参数，再用 `[Environment]::SetEnvironmentVariable(..., ..., 'Process')` 设置代理后执行目标命令。环境变量不会从子进程反向传回已经运行的 Codex。
- 启动方式和适用范围见 `network/README.md`。更改代理地址时同步更新 `network/proxy.psd1` 和 `.codex/config.toml`。
- 不在项目中记录密码、令牌或私钥；不把代理参数持久化误称为保持跨对话连接，也不把 shell 代理配置描述为桌面客户端网络修复。

# CPU_CONTROL 工程约定

- 全网最新活动运行（2026-10-22 18:40）：182830分层编译385.114秒，补边仍18.4269秒，已主动停止其PID1217，保留FAIL记录。新增cache_neureka_eval.py仅优化生成DPI适配器：所有输入包括时钟/复位不变时跳过重复eval，RTL无延迟、算法未改；未修改程序保留为.neureka_full_hier_build/obj/Vquant_network_sequential.uncached。check_full_eval_cache.py对照PASS：原版21.412秒/缓存14.816秒，两者21792字节、70824周期、55524读/8736写、完整VCD相同，build/eval_cache_validation/result.json。当前唯一活动run：build/runs/20261022_184024_mobilefacenet_full，会话69154，--reuse不编RTL，eval_adapter0.098秒；首完整补边192271周期0.140418秒，正在实际卷积，尚未全网PASS。运行器已自动验证生成模型哈希并记录eval_cache源/程序哈希；不重复启动、不回到旧运行。prepare仅完整PASS后使用。

- 全网运行续记（2026-10-22 18:28）：181742平坦编译成功416.439秒；全图第一步硬件补边仅记录DONE 1/373、192271周期、44.3264秒，单元测试另为220字节PASS，二者不可混淆。由于平坦仿真慢，已仅SIGTERM其模拟器PID621，runner保留FAIL退出记录；不是数值FAIL或全网PASS。改用Verilator配置hier_block -module neureka_conv_engine，未修改算子，独立缓存.neureka_full_hier_build；当前活动run为build/runs/20261022_182830_mobilefacenet_full，会话81694，编译/仿真中，优先检查此目录。不要再启动181742或175936。pad_hwc独立测试在build/pad_hwc_unit/result.json PASS，覆盖byte/word/反压/延迟/非法宽度/clear。

- 2026-10-22 全网进行中：用户授权先试跑完整网络。新增隔离 quant_network_sequential（单真实NEureka/DW7/后处理/硬件补边，顺序命令表，非双核并行入口）、pad_hwc_engine、gen/run/prepare_mobilefacenet_full.py、C++存储测试台 mobilefacenet_full_main.cpp、docs/mobilefacenet_full_design.md。完整112×112 person_1图整数参考已生成：51卷积+12Add、373命令、233810432 MAC、128维输出，build/mobilefacenet_full_data；诊断尺度取本图浮点，余弦0.993880不等于准确率。约20MiB实验存储保留所有中间结果，非生产SRAM容量承诺。初次20261022_175936_mobilefacenet_full在恢复时无进程/无程序/无manifest，记INTERRUPTED，尚未运行RTL，原因未确认。当前20261022_181742_mobilefacenet_full正在编译，执行会话60545；改用Verilator-O1、C++-O2、-j2，缓存.neureka_full_build。先读此run/result.json及compile.log或sim.log末尾，禁止重复启动；只有完整PASS才运行prepare制图并交付，不把整数参考生成当RTL通过。不改旧并行入口/CPU/UART/生产DATASRAM。

- 2026-10-22 独立7×7逐通道算子：新增 rtl/cnn_quant/dw7_cached_engine.sv，默认8路MAC、7行环形输入缓存、49×512字节权重缓存，UINT8输入/INT8权重/INT32输出，stride1、valid、multiplier1、通道为8倍数；未接quant_residual_scheduler或生产SoC。真实MobileFaceNet Conv_49为7×7×512→1×1×512，该形状没有相邻输出窗口；权重跨图复用与局部累加仍有效。gen_dw7_cached.py生成两张真实人脸的软件前缀特征和9×10×16重叠窗口例，接原quant_post_engine验证。最终 build/runs/20261022_172228_dw7_cached 五项real512/real512_stall/overlap16/overlap16_stall/overlap16_restart全部PASS，真实例5120字节、窗口例1920字节；第二帧权重读取6272→0，窗口输入9408→1440字节是相对无缓存逐窗口重读的访存比较，非NEureka性能对比。编译15.293秒、五仿真合计3.616秒、总20.509秒。缓存根目录.dw7_cached_build；run_dw7_cached.py --data build/dw7_cached_data --reuse校验源码哈希；prepare_dw7_cached.py生成deliverables/dw7_cached，两PNG目视检查且GTKWave各11信号通过。设计docs/dw7_cached_design.md。初次20261022_171724失败原因是TB漏采单周期error，修正TB后全测通过；保留失败记录。加载/计算/写回仍顺序，无DMA重叠；同址权重改写须强制重载，clear须取消旧存储事务；无综合/面积/时序验证，不宣称全网或既有调度器支持512通道。

- 2026-10-22 对接总说明：docs/CNN当前能力与模块对接说明_v0.1.md 区分前三层量化图片ROI与残差中间特征两个入口，列出现有program/storage端口、输出SRAM/完成/释放语义、CNN与CPU/输入/存储分工、首次联调顺序和待确认项。比较暂不纳入CNN范围。该轮仅文档，无RTL修改或新仿真；两份输入/存储要求已加总览链接。

- 2026-10-22 真实残差块：用户授权后新增隔离 rtl/cnn_quant/quant_residual_scheduler.sv（双真实NEureka/一quant_post/三槽），可变32通道分组、Add双输入汇合且不占scratch、release_pulse等待所有声明消费者完成，keep保留最终结果。gen_mobilefacenet_residual.py 使用两真实人脸软件前缀6×6×128特征，RTL Conv_5/6/7/8+Add、全64/128通道、28节点；不是像素输入或全网。实验512KiB/4banks/21客户端；scratch70000/72000/74000各8KiB，生产256KiB未改。build/runs/20261022_133125_mobilefacenet_residual 三项residual/recycle_stall/restart全部PASS，各101888字节、8Add、20释放、最终SHA c8872edf3a51e966da797d01aa9eda24b48608669d45a842a23dbf3c6eee4e59相同。周期161358/164849/161358；正常Add/卷积计算阶段重叠4836周期，节点0在主分支消费者完成后继续保留116569周期直到Add也完成才释放。压力例释放后立即覆盖0xD7并限速实例0；另在Add写回中clear后复位重装再跑。编译1303.39秒，三仿真295.96/299.43/518.48秒，总2419.03秒；会话62646已结束。缓存 .neureka_residual_build，run_mobilefacenet_residual.py --data build/mobilefacenet_residual_data --reuse校验RTL/头文件/监视器哈希；prepare_mobilefacenet_residual.py制图。deliverables/mobilefacenet_residual三图已目视检查，GTKWave13/13/7信号验证通过；control_raw.vcd原始，control.vcd增加真实掩码的可读位解码（首Add节点21，生命周期看旁路节点0）。说明 docs/mobilefacenet_residual_design.md、输入/存储对接文档已补充。释放仅通知，尚无动态地址分配器/循环输入缓存；未接生产CPU/UART，未做全网或识别准确率验证，不再跑历史大图。

- 2026-10-22 三槽流水：用户授权先增加第三临时槽，验证双卷积+后处理同时运行并记录等待。新增隔离 `rtl/cnn_quant/quant_triple_scheduler.sv`，保持两真实NEureka/一后处理/21客户端4-bank；第三8KiB槽0x3C000，运行时slot_limit=2或3，槽ID2位、状态9位，每任务6组配置（slot*192+group*96）。`scripts/gen_mobilefacenet_triple.py build/mobilefacenet_triple_data` 复用旧输入/权重/金标准只扩配置。最终 `build/runs/20261022_125620_mobilefacenet_triple` 三槽/两槽对照/限速清除复位重启全部PASS，各43520字节，最终哈希相同。周期82778/89487/86891；正常三方计算阶段重叠7619周期、实际后处理写重叠912周期，三槽分配[7,4,3]；两槽三方重叠0且槽2未使用/内容不变。新增wait_slot/dependency/engine/post和各端存储等待观察，非互斥、不能相加当总停顿。初编883.00秒；三项仿真139.49/189.56/232.18秒，总1445.36秒。运行 `scripts/run_mobilefacenet_triple.py --data build/mobilefacenet_triple_data --reuse`，缓存 `.neureka_triple_build`，校验RTL/头文件/监视器哈希；制图 `scripts/prepare_mobilefacenet_triple.py`。新TB独立推进预热限速计数，组合限速+重启已验证，不回写旧TB失败。交付 `deliverables/mobilefacenet_triple` 三视图GTKWave14/17/14信号校验通过，设计 `docs/mobilefacenet_triple_design.md`。旧两槽实现保留；仍两真实人脸ROI三层64通道SRAM预加载，无UART/CPU接入、完整残差网络或第二后处理；不要直接扩称完整网络或每类3～5算子。

- 2026-10-22 双同类实例：用户授权两个算子自动分配验证。新增隔离 `rtl/cnn_quant/quant_dual_scheduler.sv`，两套真实NEureka（各4×4）+一套量化后处理+两个槽，依赖满足后选择空闲已启用实例，双方空闲轮换优先；无图片/层固定绑定，条带两通道组留在同实例。SRAM用现有CLIENTS=21、4banks，未改仲裁或生产顶层。`scripts/run_mobilefacenet_dual.py` 默认dual/single（仅实例1）/skew（实例0限速）/restart四项；最终 `20261022_004229_mobilefacenet_dual` PASS，各43520字节、最终哈希均4a1135c4...fd9。周期89487/115900/91358/89487；两核计算阶段重叠21537周期，双核各7条带、单实例1接全部14条带；第23414周期实例0仍忙时实例1接新任务3。缓存 `.neureka_dual_build`，原始编译839.29秒，四项运行127.13/102.88/91.25/101.51秒。初次 `20261022_002254_mobilefacenet_dual` 正常/单实例已PASS，但组合 `+stall=1 +restart` 预热死等（TB限速周期在enabled前不推进），主动终止保留FAIL；不要组合这两选项，默认分开运行。后续通过 `--reuse --reuse-passed <旧运行>` 哈希校验复用已PASS前两项，不重复编译。交付 `deliverables/mobilefacenet_dual` 三视图18/17/16信号GTKWave验证通过，设计 `docs/mobilefacenet_dual_design.md`。仍为两真实人脸ROI三层全64通道SRAM预加载；两槽只容双卷积或卷积+后处理，不能三者同时；不是智能负载预测/任意3～5算子/CPU或UART接入/完整网络。下一步行就绪与输入缓冲，再按带宽预算扩算子。

- 2026-10-22 跨层条带流水：新增隔离 `rtl/cnn_quant/quant_stripe_scheduler.sv`，一套NEureka+量化后处理+两个INT32槽，预编程任务依赖图（最多32节点）；完成位在最后写响应后更新，依赖满足才发射，优先后层。两张真实人脸ROI、前三层全部64通道、14条带节点，运行 `build/runs/20261022_000428_mobilefacenet_pipeline` 并行/顺序/反压清除复位重启全部PASS，各核对43520字节且最终输出哈希一致。周期115900/147932/129286；并行计算阶段与后处理重叠22453周期，其中3237周期有后处理写握手。首次编译271.90秒、三项仿真59.00/55.99/50.12秒，总438.23秒。生成 `scripts/gen_mobilefacenet_pipeline.py build/mobilefacenet_pipeline_data`；WSL运行 `scripts/run_mobilefacenet_pipeline.py --data build/mobilefacenet_pipeline_data --reuse`，独立缓存 `.neureka_pipeline_build`；制图 `scripts/prepare_mobilefacenet_pipeline.py`。交付 `deliverables/mobilefacenet_pipeline` 三视图GTKWave实测14/15/13信号通过，规则 `docs/mobilefacenet_pipeline_design.md`。初始图像/权重SRAM预加载，后层读取真实硬件输出；只有临时槽复用，各帧各层特征区仍保留。未接生产CPU/UART、循环行缓冲、完整残差网络、7×7或全网RTL；量化尺度两图共用但仅诊断，非识别准确率校准。只有一个卷积实例，不得称多层卷积同时执行。下一步输入行就绪通知与缓冲回收，再更长网络依赖；不要重跑大图。

- 2026-10-21 23:50 小链条：DW3×3+stride2关闭内部prefetch同例PASS（默认生成器针对该组合关闭；`--force-prefetch`保留复现卡顿，第三方内部预取根因未修）。默认策略复测 `20261021_234933_neureka_model_modes` 96字节PASS。新增隔离 `rtl/cnn_quant/quant_post_engine.sv`（INT32卷积后处理/双UINT8残差、96位中间值、逐通道5字参数、一次舍入、夹紧、清除）；未接现有生产CPU/UART或两槽流水。真实权重小ROI脚本 `scripts/gen_mobilefacenet_chain.py` 使用用户person_1与固定ONNX，首层6×6×64→DW4×4×64→PW4×4×64，保留全部通道；真实硬件中间数据串接，逐层INT32/UINT8检查。WSL `scripts/run_mobilefacenet_chain.py --data build/mobilefacenet_chain_data_v2 --reuse`，独立缓存 `.neureka_chain_build`；最终 `build/runs/20261021_234938_mobilefacenet_chain` 正常/反压PASS各21792字节、68635/70434周期，另检查不可写区、参数错误和clear。初次编译289.57s，最终复用两项27.10+26.54s；没有大图/整网RTL。新浮点ROI与整网匹配最大1.29e-6，量化尺度仅本例诊断，非准确率校准。`deliverables/mobilefacenet_chain` 含说明、PNG/VCD/GTKWave16条信号实际校验通过；规则 `docs/mobilefacenet_quant_contract.md`。当前顺序小链条，不得称UART边收边算/多图流水/完整人脸识别通过。下一步接入条带调度、跨层halo/残差依赖，再扩量化与7×7。历史失败/报告保留。

- 2026-10-21 深夜 MobileFaceNet 参考基线：用户提供 `D:/code/facemodel`，四张 `person_*.jpg` 为112×112，未证明五点对齐。固定 foamliu/MobileFaceNet 提交 `a6cc9032a659b615f477833e1a70b5e7931bcccc`，TorchScript SHA256 `780e31e7c2639a0d5fdebe843f5df3ff81fda79a090164df0ff40514d172853a` 与用户目录一致；项目隔离 CPU PyTorch/ONNX 依赖 `.tools/mobilefacenet-python`。`scripts/prepare_mobilefacenet_reference.py --images D:/code/facemodel` 最终 `build/runs/20261021_232600_mobilefacenet_reference` PASS：4张真实图输出128维，双框架最大误差6.44e-6；51卷积=33PW1×1+16DW3×3+1普通3×3+1GD7×7，32ReLU6、2ReLU、12Add，BN已折叠，无MaxPool/PReLU。RGB ImageNet mean/std沿用上游val，demo约定不同需准确率阶段确认。不是INT8全网或SoC通过。`scripts/run_neureka_model_modes.py` 仅复用哈希匹配条带缓存；`20261021_232033_neureka_model_modes` PW、DW stride1、普通stride2三项PASS。补测 `20261021_232534_neureka_model_modes` **DW stride2 FAIL超时**：首任务停MATRIXVEC、无写回，2接收0完成，memory_fault=0；不可声称此组合已支持。网络3层需要此模式，优先查累计完成/预取完成握手；不擅改第三方核心或重跑大图。GD7×7九块宽累加仅CPU整数等价证明，未硬件接入。交付 `deliverables/mobilefacenet_reference/README.md`、实际算子/数值范围/结果/失败日志。下一步补DW stride2、量化约定、ReLU6/残差与实际通道padding，再小链条；不直接全网RTL。用户允许需要GPU时用test1，但本轮未连接，连接方式未确认。

- 2026-10-21 用户决定放弃 Vicuna，卷积回到 NEureka；目标是已裁剪对齐人脸、可配置固定流程、分块输入与多算子重叠，先小图验证。新增隔离 CNN 子系统 `rtl/neureka/neureka_stripe_pipeline.sv`：一套真实 NEureka + 原 ReLU + 两槽 scratch 生命周期调度，11 客户端沿用（0～8卷积、9配置、10激活），HWC 逐元素 ReLU 不需格式转换。共享 `neureka_conv_engine.sv` DRAIN 必须同时检查 `!tcdm.req`，避免 idle 桥恰好接受最后请求时提前 done；首次失败 `build/runs/20261021_224641_neureka_stripes` 保留。最终 `build/runs/20261021_225407_neureka_stripes` 四项 PASS（流水、顺序、尾块停顿、clear后复位重启），主例两张14×11 RGB→12×9×8、六条带，1728最终字节全对，6990周期 MATRIXVEC/ReLU busy重叠；首计算3154周期早于首图EOF6488周期。运行 `scripts/run_neureka_stripes.py`（WSL，缓存 `.neureka_stripes_build`，`--reuse`校验哈希），制图 `scripts/prepare_neureka_stripes.py`（Windows Python）；交付 `deliverables/neureka_stripes`，GTKWave三视图14/13/12信号验证通过。仍无CPU寄存器接入/UART/通用依赖图/多NEureka/循环输入行缓冲/真实人脸权重；合成小图只是卷积+ReLU验证，不能称完整MobileFaceNet通过。现有顺序入口保留，NVDLA/Vicuna历史文件不删除。推荐MobileFaceNet尚未下载或验证权重，需核对stride2、DW3×3、末端GDConv7×7及量化格式。不要直接重跑历史大图或继续Vicuna任务。

- 2026-10-22 用户已授权将今天连续帧及 FX8 修改、Markdown 说明和源码 ZIP 提交到现有 GitHub `moon` 分支。汇总说明 `docs/2026-10-22修改说明.md`；压缩包位于仓库根 `releases/2026-10-22/`。此前条目中“未提交/推送”描述的是实现完成当时的历史状态。发布不扩大为上板任务。

- 2026-10-22 FX8 接口：用户最终限定“只改代码，暂不考虑上板”。新增隔离入口 `rtl/fx8/face_soc_neureka_fx8_top.sv`，图像桥内部为 8 位 RX/TX、sys_clk/4、双时钟 FIFO、同协议 CRC、32 位字节使能打包；六模块其余内部接口/原 UART RTL 不变。`python scripts/run_fx8.py` 的最终 `20261022_182439_335221_fx8` 六项 PASS，真实主 CPU/桥/SRAM/调度加测试运算模型，四帧1820输出字节一致。真实核较早尝试 `fpga-cnn-moon` 下 `20261022_181204_716758_fx8` 编译展开后仍在 alignment_buffer:115、0 ps XSim 内核崩溃；最终收窄计数器未重新真实核验收。板级 XDC/工程/综合脚本只是草案，最新综合检查在 Gray 寄存器计数断言失败且未完成时序签核，不主动继续上板工作。详见 `docs/ees331_fx8_interface.md` 和 `docs/fx8_verification_20261022.md`。两份源码同步；本次未提交/推送。

- 2026-10-22 用户授权在 Neureka 分块入口实现“当前 CNN + 下一帧加载 + CPU 工作”，要求六模块 IO 连线不变。`face_soc_neureka_pipeline_top` 在原 `image_bridge_autoload` 上启用默认关闭的 SRAM 描述符模式（SRAM_BASE+0x60，五字 magic/source/destination/bytes/CRC），三线加载握手、旧固定批次入口及 CPU/IMEM/四 bank SRAM/CNN 算术 RTL 不改。驱动 `sw/neureka_pipeline/cnn_frames.h` 提供输入/输出帧 A/B 协作式所有权调度，与原中间 tile A/B 不同；错误冻结所有权、需复位，不宣称全 SRAM 硬件保护。`scripts/run_neureka_frames.py` 默认使用真实主 CPU/桥/SRAM/邮箱/tile 调度器加测试专用标量计算模型；20261022_165909_947172_neureka_frames 四项 PASS，覆盖快/慢加载、四帧1820字节、CPU工作、CRC失败不提交及九种描述符故障。旧 autoload 六项和 tile 控制回归 PASS。真实核 `--real-cores` 在本地 fpga-cnn-moon 副本的 20261022_170414_959878_neureka_frames 编译展开成功，仍在 CV32E40X alignment_buffer:115、0 ps 出现 XSim 内核崩溃，仿真 FAIL；不得宣称真实核数值、加速比或上板通过。详情 `docs/neureka_continuous_frames.md`。本次仅本地修改，两份代码同步，尚未提交/推送新改动。

- 2026-10-13 用户授权联合接入 NVDLA 与 Vicuna。新增隔离六模块入口 `rtl/hybrid/face_soc_hybrid_top.sv`，CNN 内包含原真实 NVDLA、CV32E40X＋Vicuna 2、16 KiB 局部程序 RAM、命令寄存器及单在途 SRAM 桥；原主 CPU Control/Datapath、DATASRAM、主 IMEM RTL 未改。必须通过零等待命令寄存器访问慢速配置，原 CPU 仅译码偏移0x00～0x20且不能等待CSB，扩大MMIO窗口不解决此问题。真实CPU固件三项测试在 `build/runs/20261013_211215_hybrid_soc` PASS（小卷积串联、多通道卷积串联、池化与FP32独立任务并发），另有 `20261013_210749_hybrid_adapters` 接口短回归 PASS。交付 `deliverables/hybrid_soc`，说明 `docs/hybrid_soc_integration.md`，构建 `scripts/run_hybrid_soc.py`（WSL，后续 `--reuse`，保留timed RAM）。本次 SRAM 预加载、UART 空闲，不是收图全链路。重要限制：集成配置的FP32先比较后乘法有错误，冗余加载诊断还触发看门狗；采用先乘法后比较的程序通过，但根因未彻底定位，不能宣称通用程序可靠。失败保留在 `20261013_210250_hybrid_soc` 和 `20261013_211032_hybrid_fp32_diagnostic`。辅助核程序RAM不等于恢复已放弃的主IMEM下载方案。

- 2026-10-09 GTKWave 交付：本机项目内便携版路径 `tools/gtkwave/portable/gtkwave64/bin/gtkwave.exe`（3.3.100，官方 SourceForge 包，哈希已核对）。无需再次搜索安装位置。`deliverables/gtkwave_soc_36/` 含与合并图相同顺序的36根信号、原生保存会话、GTKWave截图和 `.cmd` 启动入口；`open_gtkwave.cmd` 全程，`open_cnn_detail.cmd` 计算/读回，`open_write_detail.cmd` 四次输出写回。实际Tcl检查TOTAL/VISIBLE均36，`validation.json`保存检查结果。来源仍是20261008_230704历史仿真，不代表新一轮RTL仿真；未实施外部仅送图像的目标。准备脚本 `scripts/prepare_gtkwave_soc.py`，然后由GTKWave执行交付目录的 `export_and_verify.tcl`。

- 2026-10-08 最新实施：用户已授权按三线直连方案完善 RTL 和上电全程小任务仿真。新版隔离入口 `rtl/soc/autoload/face_soc_autoload_top.sv`、清单 `rtl/filelists/system_autoload.f`；六模块、外部7信号保留，CPU封装与主动图像桥之间仅增 `load_req / load_complete / load_error`。CPU封装内部保留数据地址0x40/0x44作控制/状态，原Control C1、生产Datapath、CNN、datasram、IMEM和clock_unit不改。完整四阶段握手、固定批次加载、包/整批CRC、失败锁定复位恢复已实现；配套真实RV32I固件及外部UART设备模型。测试 `python scripts/run_autoload_integration.py` 六项通过：上电正常闭环、包CRC、超时迟到、整批CRC、错误tag、63字节分包尾包。真实CNN执行2×2输入的1×1卷积，结果[5,-1,9,11]，不等于全模型或上板验收。说明见根目录 `SoC三线自动加载RTL与上电全流程仿真说明_小白版.md`、`docs/autoload_uart_protocol.md`。旧 `face_soc_top/system_cnn.f` 继续保留被动UART版本；不要混编为同一顶层，不恢复可写IMEM。外部器件尚未确定，新桥要求设备实现IMIO读请求/IMOR回复协议。当前是单次顺序演示固件，不宣称具备CNN忙闲硬件互锁或连续帧调度。

- 2026-10-08 历史说明方案：用户不采用“顶层MMIO分流到image_bridge”的接线稿，改用CPU与图像桥三线直连。原讨论稿为根目录 `SoC六模块增线说明_CPU与图像桥三线直连.md`，其中“仅文档、待实现”是当时状态；后续实施以上一条及新仿真说明为准。

- 2026-10-08 历史需求分析：上电后自动从外部存储数据源加载图像/资料，无需电脑运行时控制。原image_bridge是被动IMIO收包/回复；新版主动加载和小任务固件已另行实现，完整应用和实际外部器件仍待确定。固件指IMEM中的板内CPU程序，不等于电脑软件。早期分析见根目录 `上电自动读取外部数据与固件作用说明_小白版.md`，不重新启动已放弃的IMEM下载改造。

- 2026-10-08 后续决定：用户放弃可写 IMEM、独立程序下载串口及下载互锁改造，继续使用原六模块 `face_soc_top`。此前仅新增方案文档和图，未修改 RTL，无需硬件回滚；新版下载口文档仅作未实施历史稿，不得作为当前接线或开发任务。当前上电至图像处理流程见根目录 `SoC六模块从上电到图像处理的数据流_小白版.md`，其中完整应用固件、mailbox约定和全模型验收仍未完成。

- 2026-10-08 用户授权改 SRAM 时序，将仲裁并入 datasram，并实际实现 UART 图像桥和时钟复位。当前板级顶层 `rtl/soc/face_soc_top.sv` 直接实例化 `cpu_core / mobilefacenet_accelerator_top / datasram / imem_rom / image_bridge / clock_unit` 六个平级模块；`face_soc_cnn_top` 仅为计算侧测试入口。CNN 原生 mem_* 66/33 位直接接 datasram，不经过 CPU；图像桥 io_mem_* 70/35 位保留 error。datasram 内部实现 RAM、B 仲裁与完成时序，当前 `rtl/filelists/system_cnn.f` 不编译旧存储子系统、独立 sram_b_arbiter 或假 CNN 寄存器。A 口固定一拍，Control C1 与生产 Datapath 不变。CNN 原包 RTL 保持原样，XSim 仅使用 tensor_operator_engine 语法等价副本。UART 为 IMIO 分块读写/CRC32；clock_unit 不带 PLL，复位三拍同步释放。CNN 存储故障及 UART 内存超时需系统复位；LED busy 是桥忙而非 CNN busy。最新依据：顶层 `SoC顶层连线与总体IO说明_小白版.md`、`docs/uart_image_bridge_protocol.md`、`docs/soc_six_module_verification_20261008.md`。测试 `python scripts/run_cnn_integration.py` 和 `python -m unittest discover -s tb -p test_uart_image_transfer.py`。以下带日期的旧交付状态仅为历史，不得重加外置适配器/仲裁器；不能把 RTL 仿真说成上板或完整人脸识别通过。

- 设计输入是根目录两份原始 Markdown 和用户在对话中提供的架构图；用户负责 CPU_CONTROL。原始文件保留，不擅自修改生产 Datapath/CNN。
- 已按 C1/D1 实现；根据 FACE-SOC-COORD-P1，M / Control 侧已正式接受 C1 作为 v1.0 开发基线（端口/编码/RTL 不变），不再把本方确认列为待办。D1 为 Datapath 原则接受记录；三方回签、公共地址/全局复位/真实存储时序仍待共同冻结。当前正式回复在 docs/control_reply_to_P1.md，P1 原文归档在 docs/inputs/FACE-SOC-COORD-P1.md。接口说明在 docs/cpu_control_interface.md，对齐记录在 docs/control_reply_to_D1.md，D1 原文归档于 docs/inputs/CPU-DP-IF-D1.md。2026-09-17 已收到 D:\QQ\face_recognition_soc_datapath_complete.zip，真实 Control + 生产 Datapath 的独立 ADD 和混合程序 XSim 仿真通过，双方生产 RTL 未改；存储器为同步模型，CNN MMIO 为 stub，不宣称真实 CPU/CNN/FPGA 系统通过。来源、包兼容条件、执行级末尾提交 SRAM 读写与本方旧文档阶段差异见 docs/datapath_connection_review_20260917.md；兼容共享包新哈希仍待共同归档。
- 测试统一入口：`python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot`。本机实际可用工具为 Vivado XSim 2026.1，脚本已处理其启动环境；无需每次重新发现工具路径。
- 用户教程在 docs/README_TEST.md，实际结果与限制在 docs/verification_report.md。每次运行使用独立 build/runs 子目录，不能用旧 VCD/PNG 代替本次结果。
- Control 保持组合逻辑；所有跨级状态由 Datapath 持有。CNN Driver 是普通 MMIO 软件，不添加 STATUS/CONTROL 硬件端口。
- 2026-09-28 用户确认系统 B 口采用仲裁器方案：`image_io_bridge` 与 CNN memory master 都先连接 `sram_b_arbiter`，再连接 `data_sram_tdp.B`；每个主设备请求为 70 bit（req/we/addr/wdata/be），返回为 35 bit（gnt/rvalid/rdata/error），`error` 不得删除。详细开发交接见 `docs/cnn_developer_handoff_B_port_v1.md` 和 `docs/datapath_developer_handoff_memory_v1.md`。该决定不修改 Control C1；真实 wrapper、仲裁器与 CNN RTL 仍待 D/Z 交付和验收。
