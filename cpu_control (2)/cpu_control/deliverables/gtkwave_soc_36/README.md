# GTKWave：SoC 全部 36 根信号

交付日期：2026-10-09。

本目录由实际运行的 GTKWave 3.3.100 生成保存会话和截图，不是 Matplotlib 仿制界面。使用前面同一次成功仿真的 VCD，不修改 RTL、不增加内部状态信号。信号顺序与此前合并图一致。

## 在当前电脑上打开

双击以下任意文件：

| 文件 | 打开的视图 |
|---|---|
| `open_gtkwave.cmd` | 全程总览，含全部 36 根信号 |
| `open_cnn_detail.cmd` | CNN 计算至 CPU 读回的放大视图，仍含全部 36 根信号 |
| `open_write_detail.cmd` | CNN 四次输出写回放大，仍含全部 36 根信号 |

也可以在项目根目录 PowerShell 中执行：

```powershell
& .\deliverables\gtkwave_soc_36\open_gtkwave.cmd
```

GTKWave 便携版位于 `D:\cpu_control\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe`，未修改系统 PATH，也不需要重新安装。入口脚本使用相对路径寻找该便携版。

## 会话与实际截图

| 保存会话 | GTKWave 原生截图 | 时间区间（约） |
|---|---|---|
| [soc_all_36.gtkw](soc_all_36.gtkw) | [全程截图](soc_all_36.png) | 0～315 μs |
| [soc_cnn_detail.gtkw](soc_cnn_detail.gtkw) | [CNN 与 CPU 截图](soc_cnn_detail.png) | 312800～313850 ns |
| [soc_write_detail.gtkw](soc_write_detail.gtkw) | [四次写回截图](soc_write_detail.png) | 313260～313510 ns |

保存会话指定了信号顺序、总线十六进制显示、颜色、缩放和事件标记。它需要同目录的 `soc_wires.vcd` 提供实际数据，单独一个 `.gtkw` 文件不包含波形数据。

GTKWave 根据窗口像素计算缩放，实际右边界可能比上表多出几纳秒；完整数据仍保留到约 513805 ns，没有裁掉文件中的后续记录。界面最上方的 From/To 表示可查看数据的范围，不等于当前窗口横轴的左右边界。

截图直接由 GTKWave 的 `Grab To File` 导出；同名 `.ps` 是 GTKWave 原生矢量打印文件。总览中的快速信号会挤在一起，要检查数值请打开放大视图或在 GTKWave 中继续缩放。

## 这次核对了什么

程序实际回报 `TOTAL=36`、`VISIBLE=36`，全部信号已加入且在当前窗口中可见。顺序和前一张合并图逐项比对，见 [验证记录](validation.json) 和 [GTKWave 运行记录](gtkwave_validation.log)。

还通过 GTKWave 自己读取了你刚才问到的两个时刻：

| 时刻 | mem_wdata | mem_write | 含义 |
|---|---|---:|---|
| 313280 ns | 00000005 | 0 | 结果 5 暂存在线上，此时不写 SRAM |
| 313300 ns | A5A505A5 | 1 | 已合并旧字，准备整字写入 |

实际 SRAM 写提交还须看上升沿与 `mem_ready`；第一笔发生在 313305 ns。

本数据来自此前 2×2 卷积测试，仍含 UART 加载权重和任务表，不能据此认为“外部只送图像”的后续方案已经实现。

## 把文件发给别人

保留本目录的 VCD 和 GTKW 文件。对方安装 GTKWave 后，在这个目录运行：

```text
gtkwave -f soc_wires.vcd -a soc_all_36.gtkw -r soc_view.rc
```

通过 `-f` 显式指定当前目录 VCD，可覆盖保存会话中的本机历史路径。当前电脑的 `.cmd` 入口依赖项目内的便携版，对方没有同样目录时使用上面的命令即可。

工具来源：[GTKWave 官方项目 Windows 便携包](https://sourceforge.net/projects/gtkwave/files/gtkwave-3.3.100-bin-win64/gtkwave-3.3.100-bin-win64.zip/download)。下载包 SHA256：`cace98e9c1e5bb6ab74ac2c4c1a2913617b6db7071418d052d2cf999a1acf39d`，已核对一致。

本地重建入口为 `scripts/prepare_gtkwave_soc.py`，它准备会话和 Tcl；随后由 GTKWave 运行 `export_and_verify.tcl` 完成原生保存、截图和检查。菜单和 Tcl 参考 [GTKWave 官方使用手册](https://gtkwave.sourceforge.net/gtkwave.pdf)。
