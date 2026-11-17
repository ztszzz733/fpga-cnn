# 同机复现

此目录是本次实际测试的冻结快照和两图数据，不随生产代码后续改动。
需要Ubuntu-22.04 WSL、C++编译器、Python3和本机已有Verilator。

在此目录执行：

```text
python3 run_units.py
python3 run_bank_gate.py
python3 run_soc.py old
python3 run_soc.py new
```

同机Verilator路径在脚本VR变量内。每个SoC脚本先跑小图门槛，再跑两图当前129步网络。
运行会新建runs目录；请保留旧结果并选择新的目录副本复测，避免覆盖证据。
fixtures中的manifest记录所有输入和独立期望值哈希。prepare_pair.py仅作为生成来源保留；提供的数据已生成，无需再生成。
