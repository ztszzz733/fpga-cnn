# tile_8x8x32

确定性合成诊断向量，非真实模型准确率样例。形状与所有地址以layout.json为准。

- 净数据28032字节；包含保护间隔和未用上下文guard的占用结束为0x7780，逻辑检查范围32KiB。
- 输出每行256字节；DDR输出行跨度264字节；逐行命令见moves.csv。
- input/weights/params/residual为搬入数据，golden只作核对。local_initial全0xA5；ddr_initial结果区为0xD7。
- ddr_expected是完整DDR镜像期望，用于同时检查结果和邻接/行间padding保护。
- native_fixture仅供现有真实CNN/SRAM检查器：权重/参数/残差经实际SRAM A口预加载，输入经现有IO口写入，绕过了新MOVER/DDR。原RTL共享SRAM参数仍32MiB，32KiB只是本样例地址范围，不能当作新32KiB RAM已综合。

原生算子命令在tasks.json；逐通道五字参数及其零点/移位见layout.json，整数参考见tools中的脚本。所有文件哈希见manifest.json。
