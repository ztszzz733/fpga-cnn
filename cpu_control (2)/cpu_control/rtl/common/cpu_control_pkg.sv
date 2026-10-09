// C1 共享编码唯一来源；D1 原则接受，公共地址/存储时序仍待三方冻结。
// Control 与 Datapath 编译同一文件，不另建同义编码副本。无时序状态。
package cpu_control_pkg;
  localparam logic [1:0] PC_NEXT=0, PC_TARGET=1, PC_JALR=2;
  localparam logic [1:0] FWD_REG=0, FWD_WB=1, FWD_MEM=2;
  localparam logic [1:0] A_REG=0, A_PC=1, A_ZERO=2, B_REG=0, B_IMM=1;
  localparam logic [1:0] WB_ALU=0, WB_LOAD=1, WB_PC4=2;
  localparam logic [2:0] IMM_NONE=0, IMM_I=1, IMM_S=2, IMM_B=3, IMM_U=4, IMM_J=5;
  localparam logic [2:0] BR_NONE=0, BR_EQ=1, BR_NE=2, BR_LT=3, BR_GE=4, BR_LTU=5, BR_GEU=6;
  localparam logic [1:0] J_NONE=0, J_JAL=1, J_JALR=2;
  localparam logic [3:0] ALU_ADD=0, ALU_SUB=1, ALU_AND=2, ALU_OR=3, ALU_XOR=4,
                         ALU_SLT=5, ALU_SLTU=6, ALU_SLL=7, ALU_SRL=8, ALU_SRA=9;
  typedef struct packed {
    logic [3:0] alu;
    logic [1:0] src_a, src_b;
    logic regwrite, memread, memwrite;
    logic [2:0] load_type;
    logic [1:0] store_type, wb;
    logic [2:0] branch;
    logic [1:0] jump;
    logic [2:0] imm;
    logic use1, use2;
  } decode_t;
endpackage
