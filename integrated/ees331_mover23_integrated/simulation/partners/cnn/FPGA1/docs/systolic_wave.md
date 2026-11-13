# 手工核对脉动阵列波形

在项目根目录运行 `python scripts/systolic_wave.py --open`。
不加 `--open` 则只生成波形和自动对照结果。不会生成图片，不会改动加速器 RTL。

实际调用现有 `systolic_tile`、`systolic_array8` 和 `systolic_pe`，不是另写一个模拟乘法器。
只使用真实 8×8 阵列左上角 2×2 个 PE，每个 PE 计算三项；本例不包含任务队列、RAM 取数、量化。
Testbench 先从写入端口把数据装入 tile 缓冲，然后发 start。

## 数据与结果

编辑 `examples/systolic_wave.json` 后重新运行即可改变输入。
`weights` 的两行对应两个输出通道；`input_windows` 的两行对应两个输出位置的窗口，均按 k 顺序存储。

默认权重：`[1,2,3]`、`[-1,1,2]`。
默认输入窗口：`[4,5,6]`、`[7,8,9]`。
每行 bias：`10`、`-5`。

```
PE00 = 10 + 1×4 + 2×5 + 3×6 = 42
PE01 = 10 + 1×7 + 2×8 + 3×9 = 60
PE10 = -5 - 1×4 + 1×5 + 2×6 = 8
PE11 = -5 - 1×7 + 1×8 + 2×9 = 14
```

## 预选的 24 行信号

| 行 | 信号 | 含义 |
|---|---|---|
| 1 | clk | 10 ns 周期，所有计算在上升沿更新 |
| 2 | rst_n | 0 复位；1 正常运行 |
| 3 | start | 启动当前 tile 的一次计算，不是 CPU 的 MMIO START |
| 4 | busy | tile 正在初始化或计算；不代表每个 PE 都有有效乘加 |
| 5 | array_ce | 阵列时钟使能；1 允许数据与累加器更新 |
| 6 | load_bias | 1 时装 bias，这一拍不乘加 |
| 7 | run_tick | 当前 RUN 拍编号；上升沿后递增，表中使用沿前值 |
| 8 | done | 当前 tile 计算完成脉冲；不是整队列 STATUS.DONE |
| 9 | fire00 | PE00 当前输入和权重都有效，允许本次上升沿乘加 |
| 10 | w00 | PE00 当前收到的有符号权重 |
| 11 | x00 | PE00 当前收到的有符号输入 |
| 12 | acc00 | PE00 当前 INT32 累加值 |
| 13 | fire01 | PE01 本次上升沿是否有效乘加 |
| 14 | w01 | PE01 当前权重 |
| 15 | x01 | PE01 当前输入 |
| 16 | acc01 | PE01 当前 INT32 累加值 |
| 17 | fire10 | PE10 本次上升沿是否有效乘加 |
| 18 | w10 | PE10 当前权重 |
| 19 | x10 | PE10 当前输入 |
| 20 | acc10 | PE10 当前 INT32 累加值 |
| 21 | fire11 | PE11 本次上升沿是否有效乘加 |
| 22 | w11 | PE11 当前权重 |
| 23 | x11 | PE11 当前输入 |
| 24 | acc11 | PE11 当前 INT32 累加值 |

`fire` 是 Testbench 观察用的组合信号：`array_ce && !load_bias && a_valid && b_valid`，并非额外控制模块。
`fire=0` 时的 w/x 不用于计算，可能是 0、旧值或未初始化值，不需要拿它们算乘积。
默认 GTKWave 保存配置使用有符号十进制显示 w/x/acc。如果手工添加信号，请设为 Signed Decimal。

## 默认输入对应的时间

- 0～160 ns：复位并装载缓冲。
- 160～170 ns：start=1，165 ns 上升沿接受启动。
- 170～180 ns：load_bias=1，175 ns 上升沿装入 bias，acc00/01=10，acc10/11=-5。
- 185 ns：PE00 首次乘加。
- 195 ns：PE01、PE10 首次乘加。
- 205 ns：四个 PE 在同一上升沿都做一次有效乘加。
- 225 ns：四个最终结果均已得出。
- 345 ns：done=1、busy=0；355 ns：done 回到 0。

当前 tile 使用固定 8×8 阵列排空时长，depth=3 对应 3+14=17 个 RUN 周期。
因此本例 PE11 已在 225 ns 算完，但 tile 会等到 345 ns 才声明完成，期间结果保持。

对照方法：光标放在上升沿前看 fire/w/x，再放在该沿后看 acc。
例如 205 ns 之前 PE11 的 fire=1、w=-1、x=7、acc=-5；205 ns 更新后 acc=-12。
不要把沿后已经切换到下一项的 w/x 当成本沿刚刚使用的操作数。

## 生成文件

- `build/systolic_wave/systolic.vcd`：波形数据。
- `build/systolic_wave/systolic.gtkw`：24 行预选信号及显示格式，打开这个保存配置即可。
- `build/systolic_wave/comparison.md`：当前输入的逐拍人工对照表。
- `build/systolic_wave/comparison.csv`：17 拍 × 4 个 PE 的 68 项参考/RTL 对照。
- `build/systolic_wave/result.json`：验证状态与最终结果。

Python 根据 k=tick-row-column 独立检查 valid 对齐、有效操作数、INT32 回绕累加和无效拍保持。
它不会把预期结果喂给 RTL；RTL 仅收到输入、权重、bias。
