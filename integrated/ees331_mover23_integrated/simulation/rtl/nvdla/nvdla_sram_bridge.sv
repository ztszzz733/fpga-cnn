// nv_small 64-bit primary AXI-like memory port -> two existing SRAM clients.
// Independent read/write FSMs; one burst per direction. IDs and backpressure
// are retained. Partial strobes use byte stores, so adjacent bytes survive.
// This first bring-up bridge prioritizes correctness over memory bandwidth.
module nvdla_sram_bridge #(
    parameter logic [31:0] SRAM_BASE=0, SRAM_SIZE=32'h40000
)(
    input logic clk,rst_n,
    input logic arvalid,output logic arready,input logic [7:0] arid,
    input logic [3:0] arlen,input logic [31:0] araddr,
    output logic rvalid,input logic rready,output logic [7:0] rid,
    output logic rlast,output logic [63:0] rdata,
    input logic awvalid,output logic awready,input logic [7:0] awid,
    input logic [3:0] awlen,input logic [31:0] awaddr,
    input logic wvalid,output logic wready,input logic [63:0] wdata,
    input logic [7:0] wstrb,input logic wlast,
    output logic bvalid,input logic bready,output logic [7:0] bid,
    output logic [1:0] mem_valid,mem_write,mem_byte,
    output logic [63:0] mem_addr,mem_wdata,
    input logic [1:0] mem_ready,mem_response,input logic [63:0] mem_rdata,
    input logic mem_fault,output logic bridge_fault,
    output logic [2:0] read_state,write_state,
    output logic [31:0] read_beats,write_beats
);
    localparam R_IDLE=0,R_ISSUE=1,R_WAIT=2,R_REPLY=3;
    localparam W_IDLE=0,W_DATA=1,W_ISSUE=2,W_WAIT=3,W_NEXT=4,W_REPLY=5;
    logic [31:0] rd_addr,wr_addr;
    logic [3:0] rd_left,wr_left;
    logic rd_half;
    logic [63:0] wr_data;
    logic [7:0] wr_mask;
    logic [3:0] lane,step;
    function automatic logic address_bad(input logic [31:0] a,input logic [3:0] len);
        logic [32:0] last_addr;
        begin
            last_addr={1'b0,a}+(({29'd0,len}+33'd1)<<3);
            address_bad=a[2:0]!=0 || a<SRAM_BASE || last_addr>({1'b0,SRAM_BASE}+{1'b0,SRAM_SIZE});
        end
    endfunction
    assign arready=read_state==R_IDLE && !bridge_fault;
    assign awready=write_state==W_IDLE && !bridge_fault;
    assign wready=write_state==W_DATA && !bridge_fault;
    assign rvalid=read_state==R_REPLY && !bridge_fault;
    assign rlast=rd_left==0;
    assign bvalid=write_state==W_REPLY && !bridge_fault;
    always_comb begin
        mem_valid=0;mem_write=2'b10;mem_byte=0;mem_addr=0;mem_wdata=0;step=1;
        mem_addr[31:0]=rd_addr+(rd_half ? 32'd4 : 32'd0);
        if(read_state==R_ISSUE && !bridge_fault) mem_valid[0]=1;
        mem_addr[63:32]=wr_addr+{28'd0,lane};
        mem_wdata[63:32]=wr_data>>(lane*8);
        mem_byte[1]=1;
        if((lane==0 || lane==4) && ((wr_mask>>lane)&8'h0f)==8'h0f) begin
            step=4;mem_byte[1]=0;
        end
        if(write_state==W_ISSUE && lane<8 && wr_mask[lane] && !bridge_fault) mem_valid[1]=1;
    end
    always_ff @(posedge clk) begin
        if(!rst_n) begin
            read_state<=R_IDLE;write_state<=W_IDLE;bridge_fault<=0;
            rd_addr<=0;wr_addr<=0;rd_left<=0;wr_left<=0;rd_half<=0;
            rid<=0;bid<=0;rdata<=0;wr_data<=0;wr_mask<=0;lane<=0;
            read_beats<=0;write_beats<=0;
        end else begin
            if(mem_fault) bridge_fault<=1;
            case(read_state)
                R_IDLE: if(arvalid&&arready) begin
                    if(address_bad(araddr,arlen)) bridge_fault<=1;
                    rd_addr<=araddr;rd_left<=arlen;rid<=arid;rd_half<=0;read_state<=R_ISSUE;
                end
                R_ISSUE: if(mem_valid[0]&&mem_ready[0]) read_state<=R_WAIT;
                R_WAIT: if(mem_response[0]) begin
                    if(!rd_half) begin rdata[31:0]<=mem_rdata[31:0];rd_half<=1;read_state<=R_ISSUE;end
                    else begin rdata[63:32]<=mem_rdata[31:0];read_state<=R_REPLY;end
                end
                R_REPLY: if(rvalid&&rready) begin
                    read_beats<=read_beats+1;
                    if(rd_left==0) read_state<=R_IDLE;
                    else begin rd_left<=rd_left-1;rd_addr<=rd_addr+8;rd_half<=0;read_state<=R_ISSUE;end
                end
                default: read_state<=R_IDLE;
            endcase
            case(write_state)
                W_IDLE: if(awvalid&&awready) begin
                    if(address_bad(awaddr,awlen)) bridge_fault<=1;
                    wr_addr<=awaddr;wr_left<=awlen;bid<=awid;write_state<=W_DATA;
                end
                W_DATA: if(wvalid&&wready) begin
                    if(wlast!=(wr_left==0)) bridge_fault<=1;
                    wr_data<=wdata;wr_mask<=wstrb;lane<=0;write_state<=W_ISSUE;
                end
                W_ISSUE: begin
                    if(lane==8) write_state<=W_NEXT;
                    else if(!wr_mask[lane]) lane<=lane+1;
                    else if(mem_valid[1]&&mem_ready[1]) begin lane<=lane+step;write_state<=W_WAIT;end
                end
                W_WAIT: if(mem_response[1]) write_state<=W_ISSUE;
                W_NEXT: begin
                    write_beats<=write_beats+1;
                    if(wr_left==0) write_state<=W_REPLY;
                    else begin wr_left<=wr_left-1;wr_addr<=wr_addr+8;write_state<=W_DATA;end
                end
                W_REPLY: if(bvalid&&bready) write_state<=W_IDLE;
                default: write_state<=W_IDLE;
            endcase
        end
    end
endmodule
