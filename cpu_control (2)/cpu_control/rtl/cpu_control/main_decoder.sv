// 图 Main Decoder：D 级主译码，组合逻辑；默认安全零控制。
// ALU 类具体 funct 合法性由 ALU Decoder 补充，不保存流水状态。
module main_decoder (
  input logic [31:0] instr_d,
  output cpu_control_pkg::decode_t decoded,
  output logic legal_main
);
  import cpu_control_pkg::*;
  always_comb begin
    decoded='0;
    legal_main=1'b1;
    case (instr_d[6:0])
      7'h37: begin decoded.regwrite=1; decoded.src_a=A_ZERO; decoded.src_b=B_IMM; decoded.imm=IMM_U; end
      7'h17: begin decoded.regwrite=1; decoded.src_a=A_PC; decoded.src_b=B_IMM; decoded.imm=IMM_U; end
      7'h6f: begin decoded.regwrite=1; decoded.src_a=A_PC; decoded.src_b=B_IMM; decoded.imm=IMM_J; decoded.jump=J_JAL; decoded.wb=WB_PC4; end
      7'h67: begin
        if (instr_d[14:12]==3'b000) begin
          decoded.regwrite=1; decoded.src_b=B_IMM; decoded.imm=IMM_I;
          decoded.jump=J_JALR; decoded.wb=WB_PC4; decoded.use1=1;
        end else legal_main=0;
      end
      7'h63: begin
        decoded.use1=1; decoded.use2=1; decoded.imm=IMM_B;
        case (instr_d[14:12])
          0: decoded.branch=BR_EQ;
          1: decoded.branch=BR_NE;
          4: decoded.branch=BR_LT;
          5: decoded.branch=BR_GE;
          6: decoded.branch=BR_LTU;
          7: decoded.branch=BR_GEU;
          default: legal_main=0;
        endcase
      end
      7'h03: begin
        decoded.regwrite=1; decoded.memread=1; decoded.use1=1;
        decoded.src_b=B_IMM; decoded.imm=IMM_I; decoded.wb=WB_LOAD;
        case (instr_d[14:12])
          0,1,2,4,5: decoded.load_type=instr_d[14:12];
          default: legal_main=0;
        endcase
      end
      7'h23: begin
        decoded.memwrite=1; decoded.use1=1; decoded.use2=1; decoded.src_b=B_IMM; decoded.imm=IMM_S;
        case (instr_d[14:12])
          0,1,2: decoded.store_type=instr_d[13:12];
          default: legal_main=0;
        endcase
      end
      7'h13: begin decoded.regwrite=1; decoded.use1=1; decoded.src_b=B_IMM; decoded.imm=IMM_I; end
      7'h33: begin decoded.regwrite=1; decoded.use1=1; decoded.use2=1; end
      // 仅 ECALL/EBREAK 暂按项目 NOP；CSR 等编码非法。
      7'h73: if ((instr_d!=32'h00000073) && (instr_d!=32'h00100073)) legal_main=0;
      // 普通 FENCE 在固定有序模型按 NOP；FENCE.I/扩展 fm 不支持。
      7'h0f: if ((instr_d[14:12]!=0) || (instr_d[31:28]!=0)) legal_main=0;
      default: legal_main=0;
    endcase
    if (!legal_main) decoded='0;
  end
endmodule
