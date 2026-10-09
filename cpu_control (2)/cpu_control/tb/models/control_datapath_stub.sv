// TEST ONLY：固定时序、无 DMA/握手/异常的验证模型，不是生产 Datapath。
// D/E/M/W 控制与数据由本模型同步保存；先 reset，再 flush，再 enable。
// 支持 RV32I 字节/半字/字 Load/Store 的对齐测试；IMEM 组合读，Data MEM 周期末锁存到 W。
module control_datapath_stub #(
  parameter logic [31:0] RESET_PC = 32'h0000_0000 // 2026-09-28 B1开发值；D/Z回签仍待归档
) (
  input logic  clk,
  input logic  rst_n,
  output logic [31:0] instr_d,
  output logic [4:0] rs1_d,
  output logic [4:0] rs2_d,
  output logic [4:0] rd_e,
  output logic [4:0] rd_m,
  output logic [4:0] rd_w,
  output logic  regwrite_m,
  output logic  regwrite_w,
  output logic  memread_e,
  output logic  cmp_eq_e,
  output logic  cmp_lt_e,
  output logic  cmp_ltu_e,
  output logic  mul_busy,
  output logic  valid_d,
  output logic  valid_e,
  output logic  valid_m,
  output logic  valid_w,
  output logic [4:0] rs1_e,
  output logic [4:0] rs2_e,
  output logic  uses_rs1_e,
  output logic  uses_rs2_e,
  output logic [2:0] branch_type_e,
  output logic [1:0] jump_e,
  output logic  memread_m,
  input logic [1:0] pc_sel,
  input logic  pc_en,
  input logic  if_id_en,
  input logic  if_id_flush,
  input logic  id_ex_flush,
  input logic [3:0] alu_ctrl,
  input logic [1:0] alu_src_a_sel,
  input logic [1:0] alu_src_b_sel,
  input logic [1:0] fwd_a,
  input logic [1:0] fwd_b,
  input logic [1:0] fwd_store,
  input logic  regwrite_d,
  input logic  memread_d,
  input logic  memwrite_d,
  input logic [2:0] load_type_d,
  input logic [1:0] store_type_d,
  input logic [1:0] wb_sel_d,
  input logic [2:0] branch_type_d,
  input logic [1:0] jump_d,
  input logic [2:0] imm_type_d,
  input logic  uses_rs1_d,
  input logic  uses_rs2_d
);

  import cpu_control_pkg::*;
  decode_t ctrl_d, ctrl_e, ctrl_m, ctrl_w;
  logic [31:0] imem[0:255], dmem[0:255], regs[0:31];
  logic [31:0] pc_f, pc_d, pc_e, pc4_m, imm_d, imm_e;
  logic [31:0] raw1_e, raw2_e, forwarded1_e, forwarded2_e;
  logic [31:0] alu_a, alu_b, alu_result_e, result_m, store_e, store_m, wb_value;
  logic [31:0] shifted_load_m, load_value_m;
  logic [3:0] alu_ctrl_e;
  logic memwrite_m_debug;
  integer commit_count, store_count, stall_count, redirect_count;
  logic [31:0] last_store;
  integer k;
  initial begin
    for (k=0;k<256;k=k+1) begin imem[k]=0; dmem[k]=0; end
  end
  assign ctrl_d.alu=alu_ctrl;
  assign ctrl_d.src_a=alu_src_a_sel;
  assign ctrl_d.src_b=alu_src_b_sel;
  assign ctrl_d.regwrite=regwrite_d;
  assign ctrl_d.memread=memread_d;
  assign ctrl_d.memwrite=memwrite_d;
  assign ctrl_d.load_type=load_type_d;
  assign ctrl_d.store_type=store_type_d;
  assign ctrl_d.wb=wb_sel_d;
  assign ctrl_d.branch=branch_type_d;
  assign ctrl_d.jump=jump_d;
  assign ctrl_d.imm=imm_type_d;
  assign ctrl_d.use1=uses_rs1_d;
  assign ctrl_d.use2=uses_rs2_d;
  assign rs1_d=instr_d[19:15];
  assign rs2_d=instr_d[24:20];
  assign memread_e=ctrl_e.memread;
  assign memread_m=ctrl_m.memread;
  assign regwrite_m=ctrl_m.regwrite;
  assign regwrite_w=ctrl_w.regwrite;
  assign uses_rs1_e=ctrl_e.use1;
  assign uses_rs2_e=ctrl_e.use2;
  assign branch_type_e=ctrl_e.branch;
  assign jump_e=ctrl_e.jump;
  assign mul_busy=1'b0;
  assign alu_ctrl_e=ctrl_e.alu;
  assign memwrite_m_debug=ctrl_m.memwrite;
  wire [31:0] mem_forward=(ctrl_m.wb==WB_PC4) ? pc4_m : result_m;
  function automatic [31:0] forward_value(input [1:0] sel, input [31:0] original);
    case(sel)
      FWD_MEM: forward_value=mem_forward;
      FWD_WB: forward_value=wb_value;
      default: forward_value=original;
    endcase
  endfunction
  always_comb begin
    imm_d=0;
    case(imm_type_d)
      IMM_I: imm_d={{20{instr_d[31]}},instr_d[31:20]};
      IMM_S: imm_d={{20{instr_d[31]}},instr_d[31:25],instr_d[11:7]};
      IMM_B: imm_d={{19{instr_d[31]}},instr_d[31],instr_d[7],instr_d[30:25],instr_d[11:8],1'b0};
      IMM_U: imm_d={instr_d[31:12],12'b0};
      IMM_J: imm_d={{11{instr_d[31]}},instr_d[31],instr_d[19:12],instr_d[20],instr_d[30:21],1'b0};
      default: imm_d=0;
    endcase
    forwarded1_e=forward_value(fwd_a,raw1_e);
    forwarded2_e=forward_value(fwd_b,raw2_e);
    store_e=forward_value(fwd_store,raw2_e);
    cmp_eq_e=(forwarded1_e==forwarded2_e);
    cmp_lt_e=($signed(forwarded1_e)<$signed(forwarded2_e));
    cmp_ltu_e=(forwarded1_e<forwarded2_e);
    case(ctrl_e.src_a)
      A_PC: alu_a=pc_e;
      A_ZERO: alu_a=0;
      default: alu_a=forwarded1_e;
    endcase
    alu_b=(ctrl_e.src_b==B_IMM) ? imm_e : forwarded2_e;
    case(ctrl_e.alu)
      ALU_SUB: alu_result_e=alu_a-alu_b;
      ALU_AND: alu_result_e=alu_a&alu_b;
      ALU_OR: alu_result_e=alu_a|alu_b;
      ALU_XOR: alu_result_e=alu_a^alu_b;
      ALU_SLT: alu_result_e={31'b0,($signed(alu_a)<$signed(alu_b))};
      ALU_SLTU: alu_result_e={31'b0,(alu_a<alu_b)};
      ALU_SLL: alu_result_e=alu_a<<alu_b[4:0];
      ALU_SRL: alu_result_e=alu_a>>alu_b[4:0];
      ALU_SRA: alu_result_e=$signed(alu_a)>>>alu_b[4:0];
      default: alu_result_e=alu_a+alu_b;
    endcase
    shifted_load_m=dmem[result_m[9:2]]>>(result_m[1:0]*8);
    case(ctrl_m.load_type)
      3'b000: load_value_m={{24{shifted_load_m[7]}},shifted_load_m[7:0]};
      3'b001: load_value_m={{16{shifted_load_m[15]}},shifted_load_m[15:0]};
      3'b100: load_value_m={24'b0,shifted_load_m[7:0]};
      3'b101: load_value_m={16'b0,shifted_load_m[15:0]};
      default: load_value_m=dmem[result_m[9:2]];
    endcase
  end
  always @(posedge clk) begin
    if(!rst_n) begin
      pc_f<=RESET_PC;pc_d<=0;pc_e<=0;pc4_m<=0; instr_d<=0;
      valid_d<=0;valid_e<=0;valid_m<=0;valid_w<=0;
      ctrl_e<='0;ctrl_m<='0;ctrl_w<='0;
      rs1_e<=0;rs2_e<=0;rd_e<=0;rd_m<=0;rd_w<=0;
      imm_e<=0;raw1_e<=0;raw2_e<=0;result_m<=0;store_m<=0;wb_value<=0;
      commit_count<=0;store_count<=0;stall_count<=0;redirect_count<=0;last_store<=0;
      for(integer i=0;i<32;i=i+1) regs[i]<=0;
    end else begin
      regs[0]<=0;
      if(valid_w && ctrl_w.regwrite && rd_w!=0) begin
        regs[rd_w]<=wb_value;commit_count<=commit_count+1;
      end
      if(valid_m && (ctrl_m.memread || ctrl_m.memwrite)) begin
        if (result_m>=1024) $fatal(1,"stub memory address outside 1KiB range");
        if ((ctrl_m.memread && ((ctrl_m.load_type==1 || ctrl_m.load_type==5) && result_m[0])) ||
            (ctrl_m.memwrite && ctrl_m.store_type==1 && result_m[0]))
          $fatal(1,"stub halfword access is not 2-byte aligned");
        if ((ctrl_m.memread && ctrl_m.load_type==2 && result_m[1:0]!=0) ||
            (ctrl_m.memwrite && ctrl_m.store_type==2 && result_m[1:0]!=0))
          $fatal(1,"stub word access is not 4-byte aligned");
      end
      if(valid_m && ctrl_m.memwrite) begin
        case(ctrl_m.store_type)
          0: case(result_m[1:0])
            0: dmem[result_m[9:2]][7:0]<=store_m[7:0];
            1: dmem[result_m[9:2]][15:8]<=store_m[7:0];
            2: dmem[result_m[9:2]][23:16]<=store_m[7:0];
            default: dmem[result_m[9:2]][31:24]<=store_m[7:0];
          endcase
          1: if(result_m[1]) dmem[result_m[9:2]][31:16]<=store_m[15:0];
             else dmem[result_m[9:2]][15:0]<=store_m[15:0];
          default: dmem[result_m[9:2]]<=store_m;
        endcase
        store_count<=store_count+1;last_store<=store_m;
      end
      valid_w<=valid_m;ctrl_w<=ctrl_m;rd_w<=rd_m;
      wb_value <= (ctrl_m.wb==WB_LOAD && valid_m) ? load_value_m : mem_forward;
      valid_m<=valid_e;ctrl_m<=ctrl_e;rd_m<=rd_e;
      result_m<=alu_result_e;store_m<=store_e;pc4_m<=pc_e+4;
      if(id_ex_flush) begin
        valid_e<=0;ctrl_e<='0;rs1_e<=0;rs2_e<=0;rd_e<=0;
        pc_e<=0;imm_e<=0;raw1_e<=0;raw2_e<=0;
      end else begin
        valid_e<=valid_d;ctrl_e<=ctrl_d;rs1_e<=rs1_d;rs2_e<=rs2_d;rd_e<=instr_d[11:7];
        pc_e<=pc_d;imm_e<=imm_d;
        // WB->ID 旁路：保证同沿写回和读取可见。
        raw1_e <= (rs1_d==0) ? 0 : ((valid_w && regwrite_w && rd_w==rs1_d) ? wb_value : regs[rs1_d]);
        raw2_e <= (rs2_d==0) ? 0 : ((valid_w && regwrite_w && rd_w==rs2_d) ? wb_value : regs[rs2_d]);
      end
      if(if_id_flush) begin valid_d<=0;instr_d<=0;pc_d<=0; end
      else if(if_id_en) begin
        if(pc_f[1:0]!=0 || pc_f>=1024) $fatal(1,"stub fetch outside aligned 1KiB IMEM");
        instr_d<=imem[pc_f[9:2]];pc_d<=pc_f;valid_d<=(imem[pc_f[9:2]]!=0);
      end
      if(pc_en) begin
        case(pc_sel)
          PC_TARGET: pc_f<=pc_e+imm_e;
          PC_JALR: pc_f<=(forwarded1_e+imm_e)&32'hfffffffe;
          default: pc_f<=pc_f+4;
        endcase
      end
      if(!pc_en) stall_count<=stall_count+1;
      if(pc_sel!=0) redirect_count<=redirect_count+1;
    end
  end
endmodule
