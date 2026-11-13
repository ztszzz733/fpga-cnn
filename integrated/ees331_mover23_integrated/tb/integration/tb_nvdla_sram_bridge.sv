`timescale 1ns/1ps
module tb_nvdla_sram_bridge;
    logic clk=0,rst_n=0;always #5 clk=~clk;
    logic arvalid=0,arready,rvalid,rready=0,rlast,awvalid=0,awready,wvalid=0,wready,wlast=0,bvalid,bready=0;
    logic [7:0] arid=0,rid,awid=0,bid,wstrb=0;
    logic [3:0] arlen=0,awlen=0;
    logic [31:0] araddr=0,awaddr=0;
    logic [63:0] rdata,wdata=0;
    wire [1:0] mem_valid,mem_write,mem_byte,mem_ready,mem_response;
    wire [63:0] mem_addr,mem_wdata,mem_rdata;
    wire mem_fault,bridge_fault;
    wire [2:0] read_state,write_state;
    wire [31:0] read_beats,write_beats;
    logic [31:0] dmem_addr=0,dmem_wdata=32'haaaaaaaa;
    logic dmem_we=0;
    nvdla_sram_bridge #(.SRAM_SIZE(32'h1000)) dut(.*);
    datasram_banked #(.SRAM_SIZE(32'h1000),.CLIENTS(2)) mem (
        .clk,.rst_n,.dmem_addr,.dmem_wdata,.dmem_wstrb(4'hf),.dmem_re(1'b0),.dmem_we,.dmem_rdata(),
        .cnn_valid(mem_valid),.cnn_write(mem_write),.cnn_byte(mem_byte),.cnn_addr(mem_addr),.cnn_wdata(mem_wdata),
        .cnn_ready(mem_ready),.cnn_response(mem_response),.cnn_rdata(mem_rdata),.cnn_cancel(bridge_fault),.cnn_mem_fault(mem_fault),
        .io_mem_req(1'b0),.io_mem_we(1'b0),.io_mem_addr(32'd0),.io_mem_wdata(32'd0),.io_mem_be(4'd0),
        .io_mem_gnt(),.io_mem_rvalid(),.io_mem_rdata(),.io_mem_error()
    );
    task automatic beat(input logic [63:0] data,input logic [7:0] mask,input logic last);
        @(negedge clk);wdata=data;wstrb=mask;wlast=last;wvalid=1;
        do @(posedge clk);while(!wready);
        @(negedge clk);wvalid=0;
    endtask
    task automatic receive(input logic [63:0] expected,input logic last);
        wait(rvalid);@(negedge clk);
        repeat(3) begin
            if(!rvalid || rdata!==expected || rid!==8'h42 || rlast!==last) $fatal(1,"read/backpressure mismatch");
            @(negedge clk);
        end
        rready=1;@(negedge clk);rready=0;
    endtask
    initial begin
        repeat(5)@(negedge clk);rst_n=1;
        for(int i=0;i<4;i++)begin dmem_addr=i*4;dmem_we=1;@(negedge clk);end
        dmem_we=0;awvalid=1;awaddr=0;awlen=1;awid=8'h91;
        do @(posedge clk);while(!awready);
        @(negedge clk);awvalid=0;
        beat(64'h7766554433221100,8'hf5,0);
        beat(64'hffeeddccbbaa9988,8'h0f,1);
        wait(bvalid);@(negedge clk);
        repeat(3)begin if(!bvalid || bid!==8'h91)$fatal(1,"B backpressure/ID");@(negedge clk);end
        bready=1;@(negedge clk);bready=0;
        arvalid=1;araddr=0;arlen=1;arid=8'h42;
        do @(posedge clk);while(!arready);
        @(negedge clk);arvalid=0;
        receive(64'h77665544aa22aa00,0);
        receive(64'haaaaaaaabbaa9988,1);
        if(read_beats!=2 || write_beats!=2 || bridge_fault)$fatal(1,"beat counters");
        // End-of-SRAM burst must fault before producing an out-of-range request.
        arvalid=1;araddr=32'hff8;arlen=1;
        do @(posedge clk);while(!arready);
        @(negedge clk);arvalid=0;
        if(!bridge_fault || mem_valid!=0)$fatal(1,"range guard");
        $display("PASS bridge: partial strobes, 2-beat bursts, ID, R/B backpressure, range guard");$finish;
    end
    initial begin #100000;$fatal(1,"bridge timeout");end
endmodule
