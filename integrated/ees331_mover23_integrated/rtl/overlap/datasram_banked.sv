// Interleaved SRAM banks, one access per bank per cycle. CPU fixed-latency A
// access reserves its bank; CNN clients and image IO arbitrate round-robin.
// Byte stores use byte enables, never read/modify/write. Responses are owned
// per client, one cycle after acceptance, for both reads and writes.
module datasram_banked #(
    parameter logic [31:0] SRAM_BASE=0, SRAM_SIZE=32'h40000,
    parameter integer BANKS=4, CLIENTS=11
)(
    input logic clk,rst_n,
    input logic [31:0] dmem_addr,dmem_wdata,input logic [3:0] dmem_wstrb,
    input logic dmem_re,dmem_we,output logic [31:0] dmem_rdata,
    input wire [CLIENTS-1:0] cnn_valid,cnn_write,cnn_byte,
    input wire [CLIENTS*32-1:0] cnn_addr,cnn_wdata,
    output logic [CLIENTS-1:0] cnn_ready,cnn_response,
    output logic [CLIENTS*32-1:0] cnn_rdata,
    input wire cnn_cancel,output logic cnn_mem_fault,
    input logic io_mem_req,io_mem_we,input logic [31:0] io_mem_addr,io_mem_wdata,
    input logic [3:0] io_mem_be,output logic io_mem_gnt,io_mem_rvalid,
    output logic [31:0] io_mem_rdata,output logic io_mem_error
);
    localparam integer WORDS=SRAM_SIZE/4, BANK_WORDS=WORDS/BANKS;
    logic [31:0] mem[0:BANKS-1][0:BANK_WORDS-1];
    integer next_owner[0:BANKS-1],selected[0:BANKS-1];
    wire [32:0] cpu_offset={1'b0,dmem_addr}-{1'b0,SRAM_BASE};
    wire cpu_valid=cpu_offset<{1'b0,SRAM_SIZE};
    wire cpu_access=(dmem_re || dmem_we) && cpu_valid;
    wire [31:0] cpu_word={1'b0,cpu_offset[32:2]};
    wire [32:0] io_offset={1'b0,io_mem_addr}-{1'b0,SRAM_BASE};
    wire io_bad=io_offset>={1'b0,SRAM_SIZE} || io_mem_addr[1:0]!=0 ||
        (io_mem_we ? io_mem_be==0 : io_mem_be!=0);
    wire [31:0] io_word={1'b0,io_offset[32:2]};
    logic io_read_error;
    logic [CLIENTS-1:0] bad;
    integer bank,n,c;
    reg [32:0] offset;
    reg found;
    always_comb begin
        c=0;offset=0;found=0;
        bad=0;
        for(integer k=0;k<CLIENTS;k=k+1) begin
            bad[k]=({1'b0,cnn_addr[k*32+:32]}-{1'b0,SRAM_BASE})>={1'b0,SRAM_SIZE} ||
                (!cnn_byte[k] && cnn_addr[k*32+:2]!=0);
        end
        cnn_ready=0;io_mem_gnt=0;
        for(bank=0;bank<BANKS;bank=bank+1) begin
            selected[bank]=-1;found=0;
            if(rst_n && !(cpu_access && cpu_word%BANKS==bank)) begin
                for(n=0;n<CLIENTS+1;n=n+1) begin
                    c=(next_owner[bank]+n)%(CLIENTS+1);
                    if(c==CLIENTS) begin
                        if(!found && io_mem_req && (io_bad ? bank==0 : io_word%BANKS==bank)) begin
                            selected[bank]=c;found=1;io_mem_gnt=1;
                        end
                    end else begin
                        offset={1'b0,cnn_addr[c*32+:32]}-{1'b0,SRAM_BASE};
                        if(!found && cnn_valid[c] && !bad[c] && !cnn_mem_fault && !cnn_cancel &&
                            ({1'b0,offset[32:2]}%BANKS==bank)) begin
                            selected[bank]=c;found=1;cnn_ready[c]=1;
                        end
                    end
                end
            end
        end
        io_mem_error=(io_mem_gnt && io_mem_we && io_bad) || (io_mem_rvalid && io_read_error);
    end
    always_ff @(posedge clk) begin:storage
        integer b,k,owner,word_index,lane;
        reg [31:0] address,value,byte_value;
        if(!rst_n) begin
            dmem_rdata<=0;cnn_response<=0;cnn_rdata<=0;cnn_mem_fault<=0;
            io_mem_rvalid<=0;io_mem_rdata<=0;io_read_error<=0;
            for(b=0;b<BANKS;b=b+1) next_owner[b]<=0;
        end else begin
            cnn_response<=0;io_mem_rvalid<=0;
            if(dmem_re) dmem_rdata<=cpu_valid ? mem[cpu_word%BANKS][cpu_word/BANKS] : 32'd0;
            if(dmem_we && cpu_valid)
                for(lane=0;lane<4;lane=lane+1) if(dmem_wstrb[lane])
                    mem[cpu_word%BANKS][cpu_word/BANKS][lane*8+:8]<=dmem_wdata[lane*8+:8];
            if(!cnn_cancel && |(cnn_valid & bad)) cnn_mem_fault<=1;
            for(b=0;b<BANKS;b=b+1) begin
                owner=selected[b];
                if(owner>=0) begin
                    next_owner[b]<=(owner+1)%(CLIENTS+1);
                    if(owner==CLIENTS) begin
                        if(io_mem_we && !io_bad)
                            for(lane=0;lane<4;lane=lane+1) if(io_mem_be[lane])
                                mem[b][io_word/BANKS][lane*8+:8]<=io_mem_wdata[lane*8+:8];
                        if(!io_mem_we) begin
                            io_mem_rvalid<=1;io_read_error<=io_bad;
                            io_mem_rdata<=io_bad ? 32'd0 : mem[b][io_word/BANKS];
                        end
                    end else begin
                        address=cnn_addr[owner*32+:32];
                        word_index=((address-SRAM_BASE)>>2)/BANKS;
                        value=mem[b][word_index];
                        byte_value=(value>>(8*address[1:0]))&32'hff;
                        cnn_response[owner]<=1;
                        cnn_rdata[owner*32+:32]<=cnn_write[owner] ? 32'd0 :
                            cnn_byte[owner] ? {{24{byte_value[7]}},byte_value[7:0]} : value;
                        if(cnn_write[owner]) begin
                            if(cnn_byte[owner]) mem[b][word_index][address[1:0]*8+:8]<=cnn_wdata[owner*32+:8];
                            else mem[b][word_index]<=cnn_wdata[owner*32+:32];
                        end
                    end
                end
            end
            if(cnn_cancel) cnn_response<=0;
        end
    end
`ifndef SYNTHESIS
    initial assert (BANKS>=1 && (BANKS&(BANKS-1))==0 && SRAM_BASE[1:0]==0 &&
        SRAM_SIZE>=BANKS*4 && SRAM_SIZE%(BANKS*4)==0 && {1'b0,SRAM_BASE}+SRAM_SIZE<=33'h100000000)
        else $fatal(1,"invalid banked SRAM configuration");
`endif
endmodule
