// C1 shared encoding compatibility candidate.
// M/Control frozen names and decode_t are the baseline. Datapath aliases refer
// to those baseline symbols so that there is only one numeric encoding source.
package cpu_control_pkg;
  // M/Control C1 v1.0 frozen definitions.
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

  // Datapath compatibility aliases. These deliberately contain no new values.
  localparam logic [1:0] PC_SEQ=PC_NEXT;
  localparam logic [1:0] ALUA_RS1=A_REG, ALUA_PC=A_PC, ALUA_ZERO=A_ZERO;
  localparam logic [1:0] ALUB_RS2=B_REG, ALUB_IMM=B_IMM;
  localparam logic [2:0] BR_BEQ=BR_EQ, BR_BNE=BR_NE, BR_BLT=BR_LT,
                         BR_BGE=BR_GE, BR_BLTU=BR_LTU, BR_BGEU=BR_GEU;
  localparam logic [1:0] JUMP_NONE=J_NONE, JUMP_JAL=J_JAL, JUMP_JALR=J_JALR;

  // RV32I funct3 values emitted by the M/Control production decoder.
  localparam logic [2:0] LOAD_LB=3'b000, LOAD_LH=3'b001, LOAD_LW=3'b010,
                         LOAD_LBU=3'b100, LOAD_LHU=3'b101;
  localparam logic [1:0] STORE_SB=2'b00, STORE_SH=2'b01, STORE_SW=2'b10;
endpackage
