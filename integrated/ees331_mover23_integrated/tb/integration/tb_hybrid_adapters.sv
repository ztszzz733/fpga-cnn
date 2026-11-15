module tb_hybrid_adapters;
    logic clk=0;always #5 clk=~clk;
    logic rst_n=0,enable=1,req=0,we=0;
    logic [31:0] addr=0,wdata=0;logic [3:0] be=0;logic [7:0] aid=0;
    wire gnt,rvalid,error,fault,finish;wire [31:0] rdata,finish_code,reads,writes,stalls;
    wire [7:0] rid;wire [2:0] state;
    wire mem_valid,mem_write,mem_byte;wire [31:0] mem_addr,mem_wdata;
    logic mem_ready=0,mem_response=0;logic [31:0] mem_rdata=0;
    logic [31:0] words[0:15];logic grant_enable=0;
    integer commits=0;
    assign mem_ready=grant_enable && mem_valid;
    always @(posedge clk) begin
        mem_response<=mem_valid && mem_ready;
        if(mem_valid && mem_ready) begin
            commits<=commits+1;
            mem_rdata<=words[mem_addr>>2];
            if(mem_write) begin
                if(mem_byte) words[mem_addr>>2][8*mem_addr[1:0]+:8]<=mem_wdata[7:0];
                else words[mem_addr>>2]<=mem_wdata;
            end
        end
    end
    vicuna_sram_port #(.SRAM_SIZE(64)) port (
        .clk,.rst_n,.enable,.req,.we,.addr,.wdata,.be,.aid,.gnt,.rvalid,.rdata,.rid,.error,
        .mem_valid,.mem_write,.mem_byte,.mem_addr,.mem_wdata,.mem_ready,.mem_response,.mem_rdata,
        .mem_fault(1'b0),.arg_src(32'h12345678),.arg_dst(32'h20),.arg_count(32'd19),.arg_mode(32'd1),
        .finish,.finish_code,.fault,.state,.reads,.writes,.stalls
    );
    task automatic request(input bit wr,input logic [31:0] a,d,input logic [3:0] b,input logic [7:0] id);
        @(negedge clk);req=1;we=wr;addr=a;wdata=d;be=b;aid=id;
        do @(posedge clk);while(!gnt);
        @(negedge clk);req=0;
    endtask
    task automatic response(input logic [7:0] id,input bit bad,input logic [31:0] expected,input bit check_data);
        while(!rvalid) @(negedge clk);
        assert(rid==id && error==bad) else $fatal(1,"response ID/error mismatch");
        if(check_data) assert(rdata==expected) else $fatal(1,"read data mismatch");
        @(negedge clk);
    endtask
    logic [31:0] mmio_addr=0,mmio_wdata=0;logic mmio_we=0,mmio_re=0;
    wire [31:0] mmio_rdata,target_addr,target_wdata,transactions;
    wire mmio_ready,target_re,target_we,busy,done,cmd_error;
    logic target_ready=0;
    cnn_command_port #(.TIMEOUT(50)) command_port (
        .clk,.rst_n,.mmio_addr,.mmio_wdata,.mmio_re,.mmio_we,.mmio_rdata,.mmio_ready,
        .target_addr,.target_wdata,.target_re,.target_we,.target_rdata(32'hcafe1234),.target_ready,
        .busy,.done,.error(cmd_error),.transactions
    );
    task automatic csrwrite(input logic [31:0] offset,data);
        @(negedge clk);mmio_addr=32'h40000000+offset;mmio_wdata=data;mmio_we=1;
        @(negedge clk);mmio_we=0;
    endtask
    initial begin
        for(integer i=0;i<16;i++)words[i]=32'ha5a5a5a5;
        repeat(4)@(negedge clk);rst_n=1;
        request(1,0,32'h12345678,4'b0101,8'ha7);
        repeat(5) begin @(negedge clk);assert(mem_valid && mem_addr==0 && !gnt) else $fatal(1,"backpressure request changed");end
        grant_enable=1;response(8'ha7,0,0,0);
        assert(words[0]==32'ha534a578 && commits==2) else $fatal(1,"partial store corruption");
        request(0,0,0,15,8'hd3);response(8'hd3,0,32'ha534a578,1);
        request(0,32'hffff0010,0,15,8'h99);response(8'h99,0,32'h12345678,1);
        assert(commits==3 && stalls>=5) else $fatal(1,"duplicate or missing transactions");
        request(1,64,0,15,8'hbc);response(8'hbc,1,0,0);
        assert(fault && commits==3) else $fatal(1,"invalid address reached SRAM");
        csrwrite(0,32'h4000100c);csrwrite(4,32'h17);csrwrite(8,1);
        repeat(4)@(negedge clk);
        assert(busy && !done && target_we && target_addr==32'h4000100c) else $fatal(1,"mailbox command missing");
        csrwrite(0,32'h40001234);
        assert(cmd_error && target_addr==32'h4000100c) else $fatal(1,"busy overwrite was not rejected");
        target_ready=1;@(negedge clk);target_ready=0;
        assert(done && !busy && transactions==1) else $fatal(1,"completion missing");
        mmio_addr=32'h40000010;#1;assert(mmio_rdata==32'hcafe1234) else $fatal(1,"mailbox response mismatch");
        csrwrite(0,32'h50000000);csrwrite(8,2);
        assert(cmd_error && !busy) else $fatal(1,"bad command accepted");
        $display("PASS hybrid adapters: backpressure, byte masks, full IDs, address fault, command retention and response");
        $finish;
    end
    initial begin #10000;$fatal(1,"adapter timeout");end
endmodule
