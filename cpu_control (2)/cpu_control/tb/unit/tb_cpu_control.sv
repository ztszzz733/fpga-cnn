`timescale 1ns/1ps
`include "tb_config.svh"
// 独立自检入口。组合单元 + test-only Datapath 时序；非真实 CPU 联调。
module tb_cpu_control;
  import cpu_control_pkg::*;
  logic clk=0, rst_n=0, link_rst=0;
  logic [31:0] instr_d;
  logic [4:0] rs1_d;
  logic [4:0] rs2_d;
  logic [4:0] rd_e;
  logic [4:0] rd_m;
  logic [4:0] rd_w;
  logic  regwrite_m;
  logic  regwrite_w;
  logic  memread_e;
  logic  cmp_eq_e;
  logic  cmp_lt_e;
  logic  cmp_ltu_e;
  logic  mul_busy;
  logic  valid_d;
  logic  valid_e;
  logic  valid_m;
  logic  valid_w;
  logic [4:0] rs1_e;
  logic [4:0] rs2_e;
  logic  uses_rs1_e;
  logic  uses_rs2_e;
  logic [2:0] branch_type_e;
  logic [1:0] jump_e;
  logic  memread_m;
  logic [1:0] pc_sel;
  logic  pc_en;
  logic  if_id_en;
  logic  if_id_flush;
  logic  id_ex_flush;
  logic [3:0] alu_ctrl;
  logic [1:0] alu_src_a_sel;
  logic [1:0] alu_src_b_sel;
  logic [1:0] fwd_a;
  logic [1:0] fwd_b;
  logic [1:0] fwd_store;
  logic  regwrite_d;
  logic  memread_d;
  logic  memwrite_d;
  logic [2:0] load_type_d;
  logic [1:0] store_type_d;
  logic [1:0] wb_sel_d;
  logic [2:0] branch_type_d;
  logic [1:0] jump_d;
  logic [2:0] imm_type_d;
  logic  uses_rs1_d;
  logic  uses_rs2_d;
  cpu_control dut (
    .clk(clk),
    .rst_n(rst_n),
    .instr_d(instr_d),
    .rs1_d(rs1_d),
    .rs2_d(rs2_d),
    .rd_e(rd_e),
    .rd_m(rd_m),
    .rd_w(rd_w),
    .regwrite_m(regwrite_m),
    .regwrite_w(regwrite_w),
    .memread_e(memread_e),
    .cmp_eq_e(cmp_eq_e),
    .cmp_lt_e(cmp_lt_e),
    .cmp_ltu_e(cmp_ltu_e),
    .mul_busy(mul_busy),
    .valid_d(valid_d),
    .valid_e(valid_e),
    .valid_m(valid_m),
    .valid_w(valid_w),
    .rs1_e(rs1_e),
    .rs2_e(rs2_e),
    .uses_rs1_e(uses_rs1_e),
    .uses_rs2_e(uses_rs2_e),
    .branch_type_e(branch_type_e),
    .jump_e(jump_e),
    .memread_m(memread_m),
    .pc_sel(pc_sel),
    .pc_en(pc_en),
    .if_id_en(if_id_en),
    .if_id_flush(if_id_flush),
    .id_ex_flush(id_ex_flush),
    .alu_ctrl(alu_ctrl),
    .alu_src_a_sel(alu_src_a_sel),
    .alu_src_b_sel(alu_src_b_sel),
    .fwd_a(fwd_a),
    .fwd_b(fwd_b),
    .fwd_store(fwd_store),
    .regwrite_d(regwrite_d),
    .memread_d(memread_d),
    .memwrite_d(memwrite_d),
    .load_type_d(load_type_d),
    .store_type_d(store_type_d),
    .wb_sel_d(wb_sel_d),
    .branch_type_d(branch_type_d),
    .jump_d(jump_d),
    .imm_type_d(imm_type_d),
    .uses_rs1_d(uses_rs1_d),
    .uses_rs2_d(uses_rs2_d));
  cpu_control_link_example link (.clk(clk), .rst_n(link_rst));
  logic offset_rst=0;
  cpu_control_link_example #(.RESET_PC(32'h0000_0040)) offset_link
    (.clk(clk), .rst_n(offset_rst));
  logic arb_reset, arb_redirect, arb_stall;
  logic [1:0] arb_select, arb_pc;
  logic arb_pe,arb_ie,arb_if,arb_id;
  pipeline_control arb (.rst_n(arb_reset),.redirect(arb_redirect),.load_use(arb_stall),
    .redirect_sel(arb_select),.pc_en(arb_pe),.if_id_en(arb_ie),.if_id_flush(arb_if),.id_ex_flush(arb_id),.pc_sel(arb_pc));
  assign rs1_d=instr_d[19:15];
  assign rs2_d=instr_d[24:20];
  integer clk_period_ns=`TB_CLK_PERIOD_NS, reset_cycles=`TB_RESET_CYCLES;
  integer max_cycles=`TB_MAX_CYCLES, seed=`TB_SEED, random_cases=`TB_RANDOM_CASES;
  integer dump_waves=`TB_DUMP_WAVES, verbose=`TB_VERBOSE, stop_first=`TB_STOP_ON_FIRST_ERROR;
  integer cycle=0, checks=0, failures=0, cases=0, random_actual=0, decode_actual=0;
  integer fwd_a_mem=0,fwd_a_wb=0,fwd_b_mem=0,fwd_b_wb=0,fwd_store_mem=0,fwd_store_wb=0;
  integer load_use_hits=0,unready_cases=0,branch_taken[1:6],branch_not_taken[1:6];
  integer hazard_random_actual=0;
  logic [31:0] random_state;
  logic [31:0] stage_instruction=0;
  integer stage_vector_id=0;
  integer windows_fd,summary_fd,ignore_arg;
  string test_name=`TB_TEST_NAME, stage_name="all", vcd_path="waves/cpu_control.vcd", vector_path="vectors.txt";
  string stage_vector_path="stage_vectors.txt";
  string case_label="startup", negative_case="";
  real window_start;
  decode_t observed;
  assign observed.alu=alu_ctrl;
  assign observed.src_a=alu_src_a_sel;
  assign observed.src_b=alu_src_b_sel;
  assign observed.regwrite=regwrite_d;
  assign observed.memread=memread_d;
  assign observed.memwrite=memwrite_d;
  assign observed.load_type=load_type_d;
  assign observed.store_type=store_type_d;
  assign observed.wb=wb_sel_d;
  assign observed.branch=branch_type_d;
  assign observed.jump=jump_d;
  assign observed.imm=imm_type_d;
  assign observed.use1=uses_rs1_d;
  assign observed.use2=uses_rs2_d;

  initial begin
    #0.001;
    forever #(clk_period_ns/2.0) clk=~clk;
  end
  always @(posedge clk) begin
    cycle=cycle+1;
    if(cycle>max_cycles) $fatal(1,"TIMEOUT cycle=%0d max_cycles=%0d case_id=%0d scene=%s",cycle,max_cycles,cases,case_label);
  end
  task automatic ck(input string name,input logic [63:0] actual,input logic [63:0] expected);
    checks=checks+1;
    if(actual!==expected) begin
      failures=failures+1;
      $display("FAIL case_id=%0d scene=%s cycle=%0d t_ns=%0.3f signal=%s actual=%h expected=%h",cases,case_label,cycle,$realtime,name,actual,expected);
      if(stop_first) $fatal(1,"stop_on_first_error");
    end else if(verbose) $display("CHECK PASS case_id=%0d %s %s",cases,case_label,name);
  endtask
  task automatic defaults;
    rst_n=1;instr_d=32'h00000013;
    valid_d=1;valid_e=0;valid_m=0;valid_w=0;
    rd_e=0;rd_m=0;rd_w=0;rs1_e=0;rs2_e=0;
    regwrite_m=0;regwrite_w=0;memread_e=0;memread_m=0;
    uses_rs1_e=0;uses_rs2_e=0;branch_type_e=0;jump_e=0;
    cmp_eq_e=0;cmp_lt_e=0;cmp_ltu_e=0;mul_busy=0;
  endtask
  task automatic begin_case(input string label_text);
    @(negedge clk);defaults();case_label=label_text;cases=cases+1;
  endtask
  task automatic settle;
    #(clk_period_ns/4.0);
  endtask
  task automatic invariants(input bit allow_unready);
    ck("no_X_outputs", (^{observed,pc_sel,pc_en,if_id_en,if_id_flush,id_ex_flush,fwd_a,fwd_b,fwd_store})===1'bx,0);
    ck("read_write_exclusive",memread_d&&memwrite_d,0);
    ck("rs1_d_pair",rs1_d,instr_d[19:15]);ck("rs2_d_pair",rs2_d,instr_d[24:20]);
    ck("mul_busy_unsupported",mul_busy,0);
    ck("branch_jump_exclusive",valid_e&&(jump_e!=0)&&(branch_type_e!=0),0);
    ck("reserved_pc",pc_sel==3,0);ck("reserved_fwd",fwd_a==3||fwd_b==3||fwd_store==3,0);
    ck("reserved_alu_src",alu_src_a_sel==3||alu_src_b_sel>1,0);
    ck("reserved_decode",wb_sel_d==3||jump_d==3||branch_type_d==7||imm_type_d>5||alu_ctrl>9,0);
    if(!allow_unready) ck("operand_ready",dut.operand_unready,0);
  endtask
  task automatic start_window;
    window_start=$realtime;
  endtask
  task automatic end_window(input string name);
    $fdisplay(windows_fd,"%s,%0.3f,%0.3f",name,window_start,$realtime);
  endtask
  task automatic run_decode;
    integer fd,ret,id,is_random,illegal_expected;
    bit decode_window_closed;
    logic [31:0] instruction;
    logic [27:0] expectation;
    decode_t golden;
    fd=$fopen(vector_path,"r");if(!fd) $fatal(1,"Cannot open vectors: %s",vector_path);
    decode_window_closed=0;
    start_window();
    while(!$feof(fd)) begin
      ret=$fscanf(fd,"%d %h %h %d %d\n",id,instruction,expectation,illegal_expected,is_random);
      if(ret==5) begin
        begin_case($sformatf("decode_vector_%0d",id));instr_d=instruction;settle();
        golden=expectation;
        ck("alu_ctrl",alu_ctrl,golden.alu);
        ck("alu_src_a_sel",alu_src_a_sel,golden.src_a);
        ck("alu_src_b_sel",alu_src_b_sel,golden.src_b);
        ck("regwrite_d",regwrite_d,golden.regwrite);
        ck("memread_d",memread_d,golden.memread);
        ck("memwrite_d",memwrite_d,golden.memwrite);
        ck("load_type_d",load_type_d,golden.load_type);
        ck("store_type_d",store_type_d,golden.store_type);
        ck("wb_sel_d",wb_sel_d,golden.wb);
        ck("branch_type_d",branch_type_d,golden.branch);
        ck("jump_d",jump_d,golden.jump);
        ck("imm_type_d",imm_type_d,golden.imm);
        ck("uses_rs1_d",uses_rs1_d,golden.use1);
        ck("uses_rs2_d",uses_rs2_d,golden.use2);

        ck("illegal_d",dut.illegal_d,illegal_expected);invariants(0);
        if(is_random) random_actual=random_actual+1;else decode_actual=decode_actual+1;
        if(id==7) begin end_window("decode");decode_window_closed=1;end
      end else if(ret!=-1) $fatal(1,"Malformed vector row");
    end
    // 少于 8 个筛选向量时也要关闭窗口，供 decode 波形正确裁剪。
    if(!decode_window_closed) end_window("decode");
    $fclose(fd);
    ck("random_count",random_actual,random_cases);
  endtask
  task automatic run_instruction_stages;
    integer fd,ret,id,illegal_expected;
    bit check_fetch,check_decode,check_execute,check_memory,check_writeback;
    logic [31:0] instruction;
    logic [27:0] expectation;
    decode_t golden;
    string instruction_name;
    check_fetch=(stage_name=="fetch"||stage_name=="all");
    check_decode=(stage_name=="decode"||stage_name=="all");
    check_execute=(stage_name=="execute"||stage_name=="all");
    check_memory=(stage_name=="memory"||stage_name=="all");
    check_writeback=(stage_name=="writeback"||stage_name=="all");
    fd=$fopen(stage_vector_path,"r");if(!fd) $fatal(1,"Cannot open stage vectors: %s",stage_vector_path);
    start_window();
    while(!$feof(fd)) begin
      ret=$fscanf(fd,"%d %s %h %h %d\n",id,instruction_name,instruction,expectation,illegal_expected);
      if(ret==5) begin
        @(negedge clk);link_rst=0;case_label=$sformatf("instruction_stage_%0d",id);cases=cases+1;
        stage_vector_id=id;stage_instruction=instruction;golden=expectation;
        for(integer i=0;i<256;i=i+1) begin link.u_datapath_stub.imem[i]=0;link.u_datapath_stub.dmem[i]=0;end
        repeat(reset_cycles) @(negedge clk);
        link.u_datapath_stub.imem[0]=instruction;
        link.u_datapath_stub.dmem[0]=32'h80ff7f01;
        // 固定为 x1=1、x2=2；阶段向量据此让六种 Branch 都走 taken 路径。
        link.u_datapath_stub.regs[1]=1;link.u_datapath_stub.regs[2]=2;
        link_rst=1;
        if(check_fetch) begin
          settle();
          ck("stage_F_pc",link.u_datapath_stub.pc_f,0);
          ck("stage_F_instruction",link.u_datapath_stub.imem[0],instruction);
        end
        @(negedge clk);
        if(check_fetch) begin ck("stage_F_to_D_valid",link.valid_d,1);ck("stage_F_to_D_instruction",link.instr_d,instruction);end
        if(check_decode) begin
          ck("stage_D_valid",link.valid_d,1);ck("stage_D_instruction",link.instr_d,instruction);
          ck("stage_D_control",link.u_datapath_stub.ctrl_d,golden);
          ck("stage_D_illegal",link.u_control.illegal_d,illegal_expected);
        end
        @(negedge clk);
        if(check_execute) begin
          ck("stage_E_valid",link.valid_e,1);ck("stage_E_rd",link.rd_e,instruction[11:7]);
          ck("stage_E_control",link.u_datapath_stub.ctrl_e,golden);
          ck("stage_E_no_X",(^{link.u_datapath_stub.alu_result_e,link.fwd_a,link.fwd_b,link.fwd_store,link.pc_sel})===1'bx,0);
          if(golden.jump==J_JALR) ck("stage_E_pc_sel",link.pc_sel,PC_JALR);
          else if(golden.jump==J_JAL || golden.branch!=BR_NONE) ck("stage_E_pc_sel",link.pc_sel,PC_TARGET);
          else ck("stage_E_pc_sel",link.pc_sel,PC_NEXT);
        end
        @(negedge clk);
        if(check_memory) begin
          ck("stage_M_valid",link.valid_m,1);ck("stage_M_rd",link.rd_m,instruction[11:7]);
          ck("stage_M_control",link.u_datapath_stub.ctrl_m,golden);
          ck("stage_M_no_X",(^{link.u_datapath_stub.result_m,link.u_datapath_stub.store_m,link.u_datapath_stub.load_value_m})===1'bx,0);
        end
        @(negedge clk);
        if(check_writeback) begin
          ck("stage_W_valid",link.valid_w,1);ck("stage_W_rd",link.rd_w,instruction[11:7]);
          ck("stage_W_control",link.u_datapath_stub.ctrl_w,golden);
          ck("stage_W_no_X",(^link.u_datapath_stub.wb_value)===1'bx,0);
        end
        @(negedge clk);
        if(check_writeback) begin
          ck("stage_W_commit_count",link.u_datapath_stub.commit_count,golden.regwrite && instruction[11:7]!=0);
          ck("stage_W_store_count",link.u_datapath_stub.store_count,golden.memwrite);
        end
      end else if(ret!=-1) $fatal(1,"Malformed stage vector row");
    end
    link_rst=0;$fclose(fd);
    end_window($sformatf("instruction_%s",stage_name));
  endtask
  function automatic [1:0] ref_forward(input bit used,input [4:0] source);
    ref_forward=0;
    if(valid_e && used && source!=0) begin
      if(valid_m && regwrite_m && rd_m!=0 && rd_m==source) begin
        if(!memread_m) ref_forward=2;
      end else if(valid_w && regwrite_w && rd_w!=0 && rd_w==source) ref_forward=1;
    end
  endfunction
  task automatic check_forward;
    bit unready;
    unready=valid_e&&valid_m&&regwrite_m&&memread_m&&rd_m!=0&&
       ((uses_rs1_e&&rs1_e==rd_m)||(uses_rs2_e&&rs2_e==rd_m));
    ck("fwd_a",fwd_a,ref_forward(uses_rs1_e,rs1_e));
    ck("fwd_b",fwd_b,ref_forward(uses_rs2_e,rs2_e));
    ck("fwd_store",fwd_store,ref_forward(uses_rs2_e,rs2_e));
    ck("operand_unready_detected",dut.operand_unready,unready);
    if(unready) unready_cases=unready_cases+1;
    if(fwd_a==2) fwd_a_mem=fwd_a_mem+1;if(fwd_a==1) fwd_a_wb=fwd_a_wb+1;
    if(fwd_b==2) fwd_b_mem=fwd_b_mem+1;if(fwd_b==1) fwd_b_wb=fwd_b_wb+1;
    if(fwd_store==2) fwd_store_mem=fwd_store_mem+1;if(fwd_store==1) fwd_store_wb=fwd_store_wb+1;
    invariants(unready);
  endtask
  task automatic run_forward;
    start_window();
    for(integer i=0;i<16;i=i+1) begin
      begin_case($sformatf("forward_%0d",i));
      valid_e=1;valid_m=1;valid_w=1;uses_rs1_e=1;uses_rs2_e=1;
      rs1_e=5;rs2_e=5;rd_m=5;rd_w=5;regwrite_m=1;regwrite_w=1;
      case(i)
        0: begin end
        1: rd_m=6;
        2: begin rs2_e=6;rd_w=6;end
        3: begin rs1_e=6;rd_w=6;end
        4: begin rd_m=6;rd_w=7;end
        5: begin uses_rs1_e=0;uses_rs2_e=0;end
        6: valid_e=0;
        7: valid_m=0;
        8: begin valid_m=0;valid_w=0;end
        9: begin rd_m=0;rd_w=0;rs1_e=0;rs2_e=0;end
        10: memread_m=1; // 不可执行消费组合，必须识别且阻止旧 WB
        11: begin memread_m=1;rd_w=6;end
        12: regwrite_m=0;
        13: begin regwrite_m=0;regwrite_w=0;end
        14: begin rs1_e=0;rs2_e=0;end
        15: begin uses_rs1_e=0;rd_m=6;end
      endcase
      settle();check_forward();
      if(i==5) end_window("forwarding");
    end
  endtask
  function automatic [31:0] next_random;
    random_state=random_state^(random_state<<13);
    random_state=random_state^(random_state>>17);
    random_state=random_state^(random_state<<5);
    next_random=random_state;
  endfunction
  task automatic run_random_hazards;
    logic [31:0] r;
    for(integer i=0;i<random_cases && i<128;i=i+1) begin
      begin_case($sformatf("random_forward_%0d",i));r=next_random();
      valid_e=r[0];valid_m=r[1];valid_w=r[2];uses_rs1_e=r[3];uses_rs2_e=r[4];
      regwrite_m=r[5];regwrite_w=r[6];memread_m=r[7]&&regwrite_m;
      rs1_e=r[12:8];rs2_e=r[17:13];rd_m=r[22:18];rd_w=r[27:23];
      if(r[28]) rd_m=rs1_e;if(r[29]) rd_w=rs2_e;
      // 合法消费约束：尚在 MEM 的 Load 不能被当前 EX 消费。
      if(memread_m && rd_m!=0 && ((uses_rs1_e&&rs1_e==rd_m)||(uses_rs2_e&&rs2_e==rd_m))) valid_e=0;
      settle();check_forward();hazard_random_actual=hazard_random_actual+1;
    end
  endtask
  task automatic run_load_use;
    bit expected,use1,use2;
    for(integer i=0;i<16;i=i+1) begin
      begin_case($sformatf("load_use_%0d",i));valid_e=1;memread_e=1;rd_e=5;use1=1;use2=1;
      case(i)
        0: instr_d=32'h00228333; // ADD x6,x5,x2
        1: instr_d=32'h00510333; // ADD x6,x2,x5
        2: instr_d=32'h0051a023; // SW x5,0(x3)
        3: instr_d=32'h0022a023; // SW x2,0(x5)
        4: instr_d=32'h00228463; // BEQ x5,x2,+8
        5: begin instr_d=32'h00028367;use2=0;end // JALR
        6: begin instr_d=32'h00510313;use2=0;end // ADDI imm contains 5
        7: begin instr_d=32'h00528337;use1=0;use2=0;end // LUI fake sources
        8: begin instr_d=32'h0052836f;use1=0;use2=0;end // JAL fake sources
        9: begin instr_d=32'h00228333;rd_e=0;end
        10: begin instr_d=32'h00228333;valid_d=0;use1=0;use2=0;end
        11: begin instr_d=32'h00228333;valid_e=0;end
        12: begin instr_d=32'h00228333;memread_e=0;end
        13: begin instr_d=32'h00528317;use1=0;use2=0;end // AUIPC
        14: begin instr_d=32'h0002a303;use2=0;end // LW x6,0(x5)
        15: begin instr_d=32'hffffffff;use1=0;use2=0;end
      endcase
      settle();expected=valid_d&&valid_e&&memread_e&&rd_e!=0&&((use1&&rs1_d==rd_e)||(use2&&rs2_d==rd_e));
      ck("uses_rs1_d",uses_rs1_d,use1);ck("uses_rs2_d",uses_rs2_d,use2);
      ck("load_use",dut.load_use,expected);ck("pc_en",pc_en,!expected);
      ck("if_id_en",if_id_en,!expected);ck("if_id_flush",if_id_flush,0);ck("id_ex_flush",id_ex_flush,expected);
      if(expected) load_use_hits=load_use_hits+1;invariants(0);
    end
  endtask
  task automatic run_branch;
    bit expected;
    start_window();
    for(integer b=1;b<=6;b=b+1) begin
      for(integer t=0;t<2;t=t+1) begin
        begin_case($sformatf("branch_%0d_outcome_%0d",b,t));valid_e=1;branch_type_e=b[2:0];
        cmp_eq_e=(b==1)?t[0]:!t[0];cmp_lt_e=(b==3)?t[0]:!t[0];cmp_ltu_e=(b==5)?t[0]:!t[0];
        settle();expected=t[0];
        ck("pc_sel",pc_sel,expected?1:0);ck("double_flush",{if_id_flush,id_ex_flush},expected?3:0);
        if(expected) branch_taken[b]=branch_taken[b]+1;else branch_not_taken[b]=branch_not_taken[b]+1;
        invariants(0);
      end
    end
    end_window("branch_units");
    begin_case("signed_unsigned_differ");valid_e=1;branch_type_e=3;cmp_lt_e=1;cmp_ltu_e=0;settle();ck("signed_taken",pc_sel,1);
    @(negedge clk);branch_type_e=5;settle();ck("unsigned_not_taken",pc_sel,0);
    begin_case("D_branch_does_not_control_E");instr_d=32'h00208463;cmp_eq_e=1;settle();ck("no_E_no_redirect",pc_sel,0);
    begin_case("invalid_E_branch");branch_type_e=1;cmp_eq_e=1;settle();ck("invalid_branch",pc_sel,0);
  endtask
  task automatic run_jump;
    for(integer j=1;j<=2;j=j+1) begin
      begin_case($sformatf("jump_%0d",j));valid_e=1;jump_e=j[1:0];settle();
      ck("jump_pc",pc_sel,j);ck("jump_flush",{if_id_flush,id_ex_flush},3);invariants(0);
      @(negedge clk);valid_e=0;settle();ck("invalid_jump",pc_sel,0);
    end
  endtask
  task automatic run_reset;
    begin_case("reset_safety");rst_n=0;valid_e=1;jump_e=2;valid_m=1;regwrite_m=1;rd_m=5;rs1_e=5;uses_rs1_e=1;
    instr_d=32'h0051a023;settle();ck("reset_decode",observed,0);ck("reset_fwd",{fwd_a,fwd_b,fwd_store},0);
    ck("reset_gates",{pc_en,if_id_en,if_id_flush,id_ex_flush,pc_sel},6'b001100);
    for(integer bits=0;bits<8;bits=bits+1) begin
      @(negedge clk);arb_reset=bits[2];arb_redirect=bits[1];arb_stall=bits[0];arb_select=2;
      settle();
      if(!arb_reset) ck("arb_reset",{arb_pe,arb_ie,arb_if,arb_id,arb_pc},6'b001100);
      else if(arb_redirect) ck("arb_redirect_over_stall",{arb_pe,arb_ie,arb_if,arb_id,arb_pc},6'b111110);
      else if(arb_stall) ck("arb_stall",{arb_pe,arb_ie,arb_if,arb_id,arb_pc},6'b000100);
      else ck("arb_normal",{arb_pe,arb_ie,arb_if,arb_id,arb_pc},6'b110000);
    end
    begin_case("invalid_D_safe");valid_d=0;instr_d=32'h0051a023;settle();ck("invalid_D_decode",observed,0);invariants(0);
  endtask
  task automatic init_link;
    @(negedge clk);link_rst=0;
    for(integer i=0;i<256;i=i+1) begin link.u_datapath_stub.imem[i]=0;link.u_datapath_stub.dmem[i]=0;end
    repeat(reset_cycles) @(negedge clk);
    link_rst=1;
  endtask
  task automatic step_link;
    @(negedge clk);
    ck("link_operand_ready",link.u_control.operand_unready,0);
    ck("x0_constant",link.u_datapath_stub.regs[0],0);
    ck("invalid_M_no_write",!link.valid_m && link.u_datapath_stub.ctrl_m.memwrite,0);
    ck("invalid_W_no_regwrite",!link.valid_w && link.regwrite_w,0);
  endtask
  task automatic run_pipeline;
    begin_case("pipeline_load_use");init_link();start_window();
    link.u_datapath_stub.regs[2]=7;link.u_datapath_stub.dmem[0]=42;
    link.u_datapath_stub.imem[0]=32'h00002283; // LW x5,0(x0)
    link.u_datapath_stub.imem[1]=32'h00228333; // ADD x6,x5,x2
    step_link();step_link();
    ck("D_consumer",link.instr_d,32'h00228333);ck("E_load",link.memread_e,1);ck("hold_PC",link.pc_en,0);
    step_link();ck("M_load_progress",link.memread_m,1);ck("bubble_E",link.valid_e,0);ck("D_held",link.instr_d,32'h00228333);
    step_link();ck("consumer_E",link.rs1_e,5);ck("consumer_WB_forward",link.fwd_a,1);ck("WB_load_data",link.u_datapath_stub.wb_value,42);
    repeat(3) step_link();ck("load_consumer_result",link.u_datapath_stub.regs[6],49);ck("one_stall",link.u_datapath_stub.stall_count,1);
    end_window("load_use");

    begin_case("pipeline_load_store");init_link();link.u_datapath_stub.dmem[0]=91;
    link.u_datapath_stub.imem[0]=32'h00002283;link.u_datapath_stub.imem[1]=32'h00502223; // SW x5,4(x0)
    repeat(8) step_link();ck("LW_SW_data",link.u_datapath_stub.dmem[1],91);ck("LW_SW_one_stall",link.u_datapath_stub.stall_count,1);ck("one_store",link.u_datapath_stub.store_count,1);

    begin_case("pipeline_forward_store_and_WB_ID");init_link();
    link.u_datapath_stub.imem[0]=32'h00900293; // ADDI x5,0,9
    link.u_datapath_stub.imem[1]=32'h00b00293; // younger x5=11
    link.u_datapath_stub.imem[2]=32'h00502223; // SW x5,4(0)
    link.u_datapath_stub.imem[3]=32'h00500333; // ADD x6,0,x5 WB->ID read
    repeat(9) step_link();ck("youngest_store",link.u_datapath_stub.dmem[1],11);ck("WB_ID_visible",link.u_datapath_stub.regs[6],11);ck("no_stall_ALU_store",link.u_datapath_stub.stall_count,0);

    begin_case("pipeline_branch_flush");init_link();start_window();
    link.u_datapath_stub.imem[0]=32'h00000663; // BEQ 0,0,+12
    link.u_datapath_stub.imem[1]=32'h06300393; // wrong x7=99
    link.u_datapath_stub.imem[2]=32'h00702223; // wrong store
    link.u_datapath_stub.imem[3]=32'h00100413; // target x8=1
    repeat(2) step_link();ck("branch_redirect",link.pc_sel,1);
    step_link();ck("flush_D",link.valid_d,0);ck("flush_E",link.valid_e,0);ck("target_PC",link.u_datapath_stub.pc_f,12);
    repeat(5) step_link();ck("wrong_reg_not_committed",link.u_datapath_stub.regs[7],0);ck("wrong_store_not_committed",link.u_datapath_stub.store_count,0);ck("target_committed",link.u_datapath_stub.regs[8],1);ck("only_target_write",link.u_datapath_stub.commit_count,1);
    end_window("branch_flush");

    begin_case("pipeline_JAL_link");init_link();
    link.u_datapath_stub.imem[0]=32'h00c002ef; // JAL x5,+12
    link.u_datapath_stub.imem[1]=32'h06300393;link.u_datapath_stub.imem[2]=32'h00702223;
    link.u_datapath_stub.imem[3]=32'h00028313; // target consumes link
    repeat(10) step_link();ck("JAL_link_PC4",link.u_datapath_stub.regs[5],4);ck("JAL_target_consume",link.u_datapath_stub.regs[6],4);ck("JAL_wrong_store",link.u_datapath_stub.store_count,0);

    begin_case("pipeline_ALU_branch_forward");init_link();
    link.u_datapath_stub.imem[0]=32'h00100293; // x5=1
    link.u_datapath_stub.imem[1]=32'h00528663; // BEQ x5,x5,+12
    link.u_datapath_stub.imem[2]=32'h06300393;link.u_datapath_stub.imem[3]=32'h00702223;
    link.u_datapath_stub.imem[4]=32'h00100413;
    repeat(3) step_link();ck("branch_fwd_A_MEM",link.fwd_a,2);ck("branch_fwd_B_MEM",link.fwd_b,2);ck("forwarded_branch_taken",link.pc_sel,1);
    repeat(7) step_link();ck("forwarded_branch_target",link.u_datapath_stub.regs[8],1);ck("forwarded_branch_no_store",link.u_datapath_stub.store_count,0);

    begin_case("pipeline_JALR_forward_mask");init_link();
    link.u_datapath_stub.imem[0]=32'h01100293; // x5=17
    link.u_datapath_stub.imem[1]=32'h00028367; // JALR x6,x5,0 ->16
    link.u_datapath_stub.imem[2]=32'h06300393;link.u_datapath_stub.imem[3]=32'h00702223;
    link.u_datapath_stub.imem[4]=32'h00100413;
    repeat(11) step_link();ck("JALR_link_PC4",link.u_datapath_stub.regs[6],8);ck("JALR_clear_bit0",link.u_datapath_stub.regs[8],1);ck("JALR_wrong_reg",link.u_datapath_stub.regs[7],0);ck("JALR_wrong_store",link.u_datapath_stub.store_count,0);
    begin_case("pipeline_D1_safe_NOP");init_link();
    link.u_datapath_stub.imem[0]=32'h00900293; // ADDI x5,x0,9
    link.u_datapath_stub.imem[1]=32'h0ff0000f; // FENCE
    link.u_datapath_stub.imem[2]=32'h00000073; // ECALL
    link.u_datapath_stub.imem[3]=32'h00100073; // EBREAK
    link.u_datapath_stub.imem[4]=32'h025282b3; // unsupported MUL x5,x5,x5
    link.u_datapath_stub.imem[5]=32'h00503223; // illegal Store funct3=3
    link.u_datapath_stub.imem[6]=32'h00001067; // illegal JALR funct3=1
    link.u_datapath_stub.imem[7]=32'h00128313; // ADDI x6,x5,1
    repeat(13) step_link();
    ck("NOP_preserves_register",link.u_datapath_stub.regs[5],9);
    ck("NOP_next_instruction",link.u_datapath_stub.regs[6],10);
    ck("NOP_only_legal_commits",link.u_datapath_stub.commit_count,2);
    ck("NOP_no_store",link.u_datapath_stub.store_count,0);
    ck("NOP_no_redirect",link.u_datapath_stub.redirect_count,0);
    ck("NOP_no_stall",link.u_datapath_stub.stall_count,0);

    begin_case("stub_D1_RESET_PC_parameter");
    @(negedge clk);
    ck("parameter_reset_PC",offset_link.u_datapath_stub.pc_f,32'h40);
    ck("parameter_reset_valid",{offset_link.valid_d,offset_link.valid_e,offset_link.valid_m,offset_link.valid_w},0);
    offset_link.u_datapath_stub.imem[0]=32'h06300393; // must not execute address zero
    offset_link.u_datapath_stub.imem[16]=32'h00000297; // AUIPC x5,0 -> 0x40
    offset_link.u_datapath_stub.imem[17]=32'h00128313; // ADDI x6,x5,1
    offset_rst=1;
    @(negedge clk);
    ck("parameter_first_fetch_PC",offset_link.u_datapath_stub.pc_d,32'h40);
    ck("parameter_first_instruction",offset_link.instr_d,32'h00000297);
    repeat(6) @(negedge clk);
    ck("parameter_AUIPC",offset_link.u_datapath_stub.regs[5],32'h40);
    ck("parameter_consumer",offset_link.u_datapath_stub.regs[6],32'h41);
    ck("parameter_skips_zero",offset_link.u_datapath_stub.regs[7],0);
    ck("parameter_commits",offset_link.u_datapath_stub.commit_count,2);
    // Assert reset between edges: PC changes only on the next rising edge.
    offset_rst=0;
    #1;
    ck("parameter_reset_is_synchronous",offset_link.u_datapath_stub.pc_f,32'h5c);
    @(negedge clk);
    ck("parameter_runtime_reset_PC",offset_link.u_datapath_stub.pc_f,32'h40);
    ck("parameter_runtime_reset_valid",{offset_link.valid_d,offset_link.valid_e,offset_link.valid_m,offset_link.valid_w},0);

    begin_case("stub_flush_over_enable");init_link();link.u_datapath_stub.imem[0]=32'h00100293;
    step_link();ck("D_valid_before_forced_flush",link.valid_d,1);
    // 仅验证注入：生产模块之间没有层级引用或 force。
    force link.if_id_en=0;force link.if_id_flush=1;force link.id_ex_flush=1;
    step_link();ck("flush_beats_disabled_enable",link.valid_d,0);ck("flush_clears_IR",link.instr_d,0);
    release link.if_id_en;release link.if_id_flush;release link.id_ex_flush;
    @(negedge clk);link_rst=0;step_link();ck("runtime_reset_PC",link.u_datapath_stub.pc_f,0);ck("runtime_reset_valid",{link.valid_d,link.valid_e,link.valid_m,link.valid_w},0);
  endtask
  initial begin
    ignore_arg=$value$plusargs("CLK_PERIOD_NS=%d",clk_period_ns);
    ignore_arg=$value$plusargs("RESET_CYCLES=%d",reset_cycles);
    ignore_arg=$value$plusargs("MAX_CYCLES=%d",max_cycles);
    ignore_arg=$value$plusargs("SEED=%d",seed);
    ignore_arg=$value$plusargs("RANDOM_CASES=%d",random_cases);
    ignore_arg=$value$plusargs("TEST_NAME=%s",test_name);
    ignore_arg=$value$plusargs("STAGE_NAME=%s",stage_name);
    ignore_arg=$value$plusargs("DUMP_WAVES=%d",dump_waves);
    ignore_arg=$value$plusargs("VERBOSE=%d",verbose);
    ignore_arg=$value$plusargs("STOP_ON_FIRST_ERROR=%d",stop_first);
    ignore_arg=$value$plusargs("VCD_PATH=%s",vcd_path);
    ignore_arg=$value$plusargs("VECTOR_PATH=%s",vector_path);
    ignore_arg=$value$plusargs("STAGE_VECTOR_PATH=%s",stage_vector_path);
    ignore_arg=$value$plusargs("NEGATIVE=%s",negative_case);
    random_state=(seed==0)?32'h6d2b79f5:seed;
    if(clk_period_ns<2 || clk_period_ns%2 || reset_cycles<2 || max_cycles<1 || random_cases<0)
      $fatal(1,"Invalid runtime parameters");
    if(!(test_name=="all"||test_name=="decode"||test_name=="instruction"||test_name=="forward"||test_name=="load_use"||test_name=="branch"||test_name=="jump"||test_name=="reset"||test_name=="pipeline")) $fatal(1,"Unknown TEST_NAME");
    if(!(stage_name=="fetch"||stage_name=="decode"||stage_name=="execute"||stage_name=="memory"||stage_name=="writeback"||stage_name=="all")) $fatal(1,"Unknown STAGE_NAME");
    for(integer i=1;i<=6;i=i+1) begin branch_taken[i]=0;branch_not_taken[i]=0;end
    windows_fd=$fopen("case_windows.csv","w");if(!windows_fd) $fatal(1,"Cannot write case windows");
`ifndef XSIM
    if(dump_waves) begin $dumpfile(vcd_path);$dumpvars(0,tb_cpu_control);end
`endif
    defaults();rst_n=0;arb_reset=0;arb_redirect=0;arb_stall=0;arb_select=0;
    $display("CONFIG test=%s seed=%0d random_cases=%0d clk_ns=%0d reset_cycles=%0d max_cycles=%0d",test_name,seed,random_cases,clk_period_ns,reset_cycles,max_cycles);
    repeat(reset_cycles) @(negedge clk);rst_n=1;
    if(negative_case=="mul_busy") begin begin_case("negative_mul_busy");mul_busy=1;settle();invariants(0);end
    if(test_name=="instruction") run_instruction_stages();
    if(test_name=="all"||test_name=="decode") run_decode();
    if(test_name=="all"||test_name=="forward") run_forward();
    if(test_name=="all"||test_name=="forward") run_random_hazards();
    if(test_name=="all"||test_name=="load_use") run_load_use();
    if(test_name=="all"||test_name=="branch") run_branch();
    if(test_name=="all"||test_name=="jump") run_jump();
    if(test_name=="all"||test_name=="reset") run_reset();
    if(test_name=="all"||test_name=="pipeline"||test_name=="load_use"||test_name=="branch"||test_name=="jump") run_pipeline();
    summary_fd=$fopen("tb_summary.json","w");if(!summary_fd) $fatal(1,"Cannot write summary");
    $fdisplay(summary_fd,"{\"cases\":%0d,\"checks\":%0d,\"failures\":%0d,\"seed\":%0d,\"random_actual\":%0d,\"decode_directed\":%0d,\"cycles\":%0d,",cases,checks,failures,seed,random_actual,decode_actual,cycle);
    $fdisplay(summary_fd,"\"hazard_random_actual\":%0d,",hazard_random_actual);
    $fdisplay(summary_fd,"\"forward_counts\":{\"A_MEM\":%0d,\"A_WB\":%0d,\"B_MEM\":%0d,\"B_WB\":%0d,\"Store_MEM\":%0d,\"Store_WB\":%0d},\"load_use_hits\":%0d,\"unready_detected\":%0d,",fwd_a_mem,fwd_a_wb,fwd_b_mem,fwd_b_wb,fwd_store_mem,fwd_store_wb,load_use_hits,unready_cases);
    $fwrite(summary_fd,"\"branches\":[");
    for(integer i=1;i<=6;i=i+1) begin
      $fwrite(summary_fd,"{\"type\":%0d,\"taken\":%0d,\"not_taken\":%0d}",i,branch_taken[i],branch_not_taken[i]);
      if(i!=6) $fwrite(summary_fd,",");
    end
    $fdisplay(summary_fd,"]}");$fclose(summary_fd);$fclose(windows_fd);
    $display("SUMMARY cases=%0d checks=%0d random=%0d seed=%0d failures=%0d",cases,checks,random_actual,seed,failures);
    if(failures) $fatal(1,"FAIL");
    $display("PASS CPU_CONTROL %s",test_name);$finish;
  end
endmodule
