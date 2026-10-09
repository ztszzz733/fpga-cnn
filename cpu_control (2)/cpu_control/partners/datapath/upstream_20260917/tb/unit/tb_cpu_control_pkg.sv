module tb_cpu_control_pkg;
  import cpu_control_pkg::*;
  int errors;
  decode_t decoded;

  task automatic check(input logic condition, input string message);
    if (!condition) begin errors++; $error("FAIL: %s", message); end
  endtask

  initial begin
    errors=0; decoded='0;
    check(PC_NEXT===2'd0 && PC_TARGET===2'd1 && PC_JALR===2'd2, "M PC encodings");
    check(A_REG===2'd0 && A_PC===2'd1 && A_ZERO===2'd2, "M ALU A encodings");
    check(B_REG===2'd0 && B_IMM===2'd1, "M ALU B encodings");
    check(FWD_REG===2'd0 && FWD_WB===2'd1 && FWD_MEM===2'd2, "forward encodings");
    check(WB_ALU===2'd0 && WB_LOAD===2'd1 && WB_PC4===2'd2, "WB encodings");
    check(IMM_NONE===3'd0 && IMM_I===3'd1 && IMM_S===3'd2 && IMM_B===3'd3 &&
          IMM_U===3'd4 && IMM_J===3'd5, "immediate encodings");
    check(BR_NONE===3'd0 && BR_EQ===3'd1 && BR_NE===3'd2 && BR_LT===3'd3 &&
          BR_GE===3'd4 && BR_LTU===3'd5 && BR_GEU===3'd6, "M branch encodings");
    check(J_NONE===2'd0 && J_JAL===2'd1 && J_JALR===2'd2, "M jump encodings");
    check(ALU_ADD===4'd0 && ALU_SUB===4'd1 && ALU_AND===4'd2 && ALU_OR===4'd3 &&
          ALU_XOR===4'd4 && ALU_SLT===4'd5 && ALU_SLTU===4'd6 && ALU_SLL===4'd7 &&
          ALU_SRL===4'd8 && ALU_SRA===4'd9, "all ALU encodings");

    check(PC_SEQ===PC_NEXT, "PC_SEQ alias");
    check(ALUA_RS1===A_REG && ALUA_PC===A_PC && ALUA_ZERO===A_ZERO, "ALU A aliases");
    check(ALUB_RS2===B_REG && ALUB_IMM===B_IMM, "ALU B aliases");
    check(BR_BEQ===BR_EQ && BR_BNE===BR_NE && BR_BLT===BR_LT && BR_BGE===BR_GE &&
          BR_BLTU===BR_LTU && BR_BGEU===BR_GEU, "branch aliases");
    check(JUMP_NONE===J_NONE && JUMP_JAL===J_JAL && JUMP_JALR===J_JALR, "jump aliases");
    check(LOAD_LB===3'b000 && LOAD_LH===3'b001 && LOAD_LW===3'b010 &&
          LOAD_LBU===3'b100 && LOAD_LHU===3'b101, "load funct3 encodings");
    check(STORE_SB===2'b00 && STORE_SH===2'b01 && STORE_SW===2'b10,
          "store funct3 encodings");

    decoded.alu=ALU_SRA; decoded.src_a=A_PC; decoded.src_b=B_IMM;
    decoded.regwrite=1; decoded.memread=1; decoded.memwrite=0;
    decoded.load_type=LOAD_LHU; decoded.store_type=STORE_SH; decoded.wb=WB_LOAD;
    decoded.branch=BR_GEU; decoded.jump=J_JALR; decoded.imm=IMM_I;
    decoded.use1=1; decoded.use2=0;
    check(decoded.alu===ALU_SRA && decoded.src_a===A_PC && decoded.src_b===B_IMM,
          "decode_t ALU/source fields");
    check(decoded.regwrite && decoded.memread && !decoded.memwrite,
          "decode_t side-effect fields");
    check(decoded.load_type===LOAD_LHU && decoded.store_type===STORE_SH &&
          decoded.wb===WB_LOAD && decoded.branch===BR_GEU && decoded.jump===J_JALR &&
          decoded.imm===IMM_I && decoded.use1 && !decoded.use2,
          "decode_t metadata fields");
    check($bits(PC_NEXT)==2 && $bits(A_REG)==2 && $bits(B_REG)==2 &&
          $bits(FWD_REG)==2 && $bits(WB_ALU)==2, "two-bit widths");
    check($bits(IMM_NONE)==3 && $bits(BR_NONE)==3 && $bits(LOAD_LB)==3,
          "three-bit widths");
    check($bits(ALU_ADD)==4 && $bits(STORE_SB)==2 && $bits(decoded)==28,
          "ALU/store/decode_t widths");

    if (errors!=0) $fatal(1, "cpu_control_pkg compatibility failures: %0d", errors);
    $display("PASS: cpu_control_pkg compatibility");
    $finish;
  end
endmodule
