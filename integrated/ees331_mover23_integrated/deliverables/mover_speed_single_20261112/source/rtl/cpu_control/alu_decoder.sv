// 图 ALU Decoder：D 级组合译码。非 ALU 类返回 ADD/合法，不误否决主译码。
// 完整检查 funct7；非法值返回 ADD/不合法，顶层清完整控制字。
module alu_decoder (
  input logic [6:0] opcode,
  input logic [2:0] funct3,
  input logic [6:0] funct7,
  output logic [3:0] alu_decoded,
  output logic legal_alu
);
  import cpu_control_pkg::*;
  always_comb begin
    alu_decoded=ALU_ADD; legal_alu=1;
    if (opcode==7'h33) begin
      case ({funct7,funct3})
        {7'h00,3'h0}: alu_decoded=ALU_ADD;
        {7'h20,3'h0}: alu_decoded=ALU_SUB;
        {7'h00,3'h1}: alu_decoded=ALU_SLL;
        {7'h00,3'h2}: alu_decoded=ALU_SLT;
        {7'h00,3'h3}: alu_decoded=ALU_SLTU;
        {7'h00,3'h4}: alu_decoded=ALU_XOR;
        {7'h00,3'h5}: alu_decoded=ALU_SRL;
        {7'h20,3'h5}: alu_decoded=ALU_SRA;
        {7'h00,3'h6}: alu_decoded=ALU_OR;
        {7'h00,3'h7}: alu_decoded=ALU_AND;
        default: legal_alu=0;
      endcase
    end else if (opcode==7'h13) begin
      case (funct3)
        0: alu_decoded=ALU_ADD;
        2: alu_decoded=ALU_SLT;
        3: alu_decoded=ALU_SLTU;
        4: alu_decoded=ALU_XOR;
        6: alu_decoded=ALU_OR;
        7: alu_decoded=ALU_AND;
        1: if (funct7==7'h00) alu_decoded=ALU_SLL; else legal_alu=0;
        5: case (funct7)
          7'h00: alu_decoded=ALU_SRL;
          7'h20: alu_decoded=ALU_SRA;
          default: legal_alu=0;
        endcase
        default: legal_alu=0;
      endcase
    end
    if (!legal_alu) alu_decoded=ALU_ADD;
  end
endmodule
