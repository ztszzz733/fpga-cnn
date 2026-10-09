// USER EDIT BEGIN：运行参数均可由脚本/plusargs 覆盖；修改此文件需重新编译。
`define TB_CLK_PERIOD_NS 10 // 时钟周期 ns，正偶数，最小 2
`define TB_RESET_CYCLES 3  // 完整复位周期，至少 2
`define TB_MAX_CYCLES 10000 // 全局超时，超过即失败
`define TB_SEED 1
`define TB_RANDOM_CASES 1000 // 随机译码数量，可为 0
`define TB_TEST_NAME "all" // decode/instruction/forward/load_use/branch/jump/reset/pipeline/all
`define TB_DUMP_WAVES 1
`define TB_VERBOSE 0
`define TB_STOP_ON_FIRST_ERROR 1
// USER EDIT END：32 位指令、5 位编号、C1 编码与 MEM 时序不是可调参数。
