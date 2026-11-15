// CPU-loadable instruction RAM belongs to CNN's auxiliary core, not main IMEM.
module vicuna_programmable #(
    parameter logic [31:0] BASE=32'h40040000,SRAM_BASE=0,SRAM_SIZE=32'h40000,
    parameter integer PROGRAM_BYTES=16384,MAX_CYCLES=200000
)(
    input logic clk,rst_n,
    input logic [31:0] cfg_addr,cfg_wdata,input logic cfg_re,cfg_we,
    output logic [31:0] cfg_rdata,output wire cfg_ready,
    output wire mem_valid,mem_write,mem_byte,
    output wire [31:0] mem_addr,mem_wdata,
    input logic mem_ready,mem_response,input logic [31:0] mem_rdata,
    input logic mem_fault,
    output logic busy,done,fault,output logic [31:0] result_code,cycles,jobs,
    output wire [2:0] memory_state,
    output wire [31:0] reads,writes,stalls,pending_registers
);
    logic [31:0] program_ram[0:PROGRAM_BYTES/4-1];
    logic [31:0] src,dst,count,mode;
    logic loaded,config_error;
    wire [31:0] offset=cfg_addr-BASE;
    wire prog_hit=offset>=32'h1000 && offset<32'h1000+PROGRAM_BYTES && offset[1:0]==0;
    wire core_reset=rst_n && busy && !fault;
    wire ireq;wire [31:0] iaddr;
    logic irvalid,ierror;logic [31:0] irdata;
    wire req[0:0],we[0:0];wire [31:0] addr[0:0],wdata[0:0];wire [3:0] be[0:0];
    wire [7:0] aid[0:0],rid[0:0];wire gnt[0:0],rvalid[0:0],err[0:0];wire [31:0] rdata[0:0];
    wire finished,port_fault;wire [31:0] finish_code;
    assign cfg_ready=1;
    always_comb begin
        case(offset)
            0:cfg_rdata={28'b0,config_error,fault,done,busy};
            4:cfg_rdata=src;8:cfg_rdata=dst;12:cfg_rdata=count;16:cfg_rdata=mode;
            20:cfg_rdata=result_code;24:cfg_rdata=cycles;28:cfg_rdata=jobs;
            default:cfg_rdata=32'hdeadbad0;
        endcase
    end
    always_ff @(posedge clk) begin
        if(!rst_n) begin
            src<=0;dst<=0;count<=0;mode<=0;busy<=0;done<=0;fault<=0;
            loaded<=0;config_error<=0;result_code<=0;cycles<=0;jobs<=0;
            irvalid<=0;ierror<=0;irdata<=32'h13;
        end else begin
            irvalid<=core_reset && ireq;
            ierror<=ireq && (iaddr>=PROGRAM_BYTES || iaddr[1:0]!=0);
            if(core_reset && ireq) irdata<=iaddr<PROGRAM_BYTES ? program_ram[iaddr>>2] : 32'h13;
            if(busy) begin
                cycles<=cycles+1;
                if(finished) begin
                    busy<=0;done<=1;result_code<=finish_code;jobs<=jobs+1;
                    if(finish_code!=0) fault<=1;
                end else if(port_fault || cycles==MAX_CYCLES-1) begin
                    busy<=0;done<=1;fault<=1;result_code<=32'hdead0003;
                end
            end
            if(cfg_we) begin
                if(busy) config_error<=1;
                else if(prog_hit) begin program_ram[(offset-32'h1000)>>2]<=cfg_wdata;loaded<=1;end
                else case(offset)
                    0: if(cfg_wdata==1 && loaded && !fault) begin
                        busy<=1;done<=0;config_error<=0;result_code<=0;cycles<=0;
                    end else config_error<=1;
                    4:src<=cfg_wdata;8:dst<=cfg_wdata;12:count<=cfg_wdata;16:mode<=cfg_wdata;
                    default:config_error<=1;
                endcase
            end
        end
    end
    vicuna_soc_core #(.MEM_W(32),.VMEM_W(32),.MEM_PORTS(1),.OBI_ID_WIDTH(8)) core (
        .clk_i(clk),.rst_ni(core_reset),.mem_req_o(req),.mem_addr_o(addr),.mem_we_o(we),
        .mem_be_o(be),.mem_wdata_o(wdata),.mem_aid_o(aid),.mem_gnt_i(gnt),
        .mem_rvalid_i(rvalid),.mem_err_i(err),.mem_rdata_i(rdata),.mem_rid_i(rid),
        .pend_vreg_wr_map_o(pending_registers),.mem_ireq_o(ireq),.mem_iaddr_o(iaddr),
        .mem_irvalid_i(irvalid),.mem_ierr_i(ierror),.mem_irdata_i(irdata)
    );
    vicuna_sram_port #(.SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE)) memory_port (
        .clk,.rst_n,.enable(core_reset),.req(req[0]),.we(we[0]),.addr(addr[0]),
        .wdata(wdata[0]),.be(be[0]),.aid(aid[0]),.gnt(gnt[0]),.rvalid(rvalid[0]),
        .rdata(rdata[0]),.rid(rid[0]),.error(err[0]),.mem_valid,.mem_write,.mem_byte,
        .mem_addr,.mem_wdata,.mem_ready,.mem_response,.mem_rdata,.mem_fault,
        .arg_src(src),.arg_dst(dst),.arg_count(count),.arg_mode(mode),
        .finish(finished),.finish_code,.fault(port_fault),.state(memory_state),.reads,.writes,.stalls
    );
endmodule
