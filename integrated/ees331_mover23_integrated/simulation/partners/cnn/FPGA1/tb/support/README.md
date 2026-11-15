# 独立阵列测试支撑

`systolic_array8.sv` 和 `systolic_tile.sv` 用于矩阵乘法、暂停复位和逐拍教学波形测试。
它们不属于当前顶层硬件，未列入 `rtl/files.f`。
实际顶层使用 `rtl/systolic_shared_array8.sv` 和两个 `rtl/systolic_tile_driver.sv`。
