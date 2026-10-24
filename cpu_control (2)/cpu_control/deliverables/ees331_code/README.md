# EES331 DDR/cache 代码交付

代码已按七页接线图接入新 CNN，并通过四图小网络的真实六模块仿真。

主入口：[face_soc_ees331_top.sv](../../rtl/soc/ees331/face_soc_ees331_top.sv)；[文件清单](../../rtl/filelists/system_ees331.f)；[完整改动与验证说明](../../docs/ees331_code_integration.md)。

evidence 保存本次最终 PASS 原始结果、数值输出和有限日志；verification_index.json 记录来源。不是 DDR 版完整 MobileFaceNet、整机资源/时序或上板验收。
