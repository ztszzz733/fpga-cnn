`timescale 1ns/1ps
module tb_image_load_descriptor;
    logic clk=0;always #5 clk=~clk;
    logic rst_n=0,uart_rx=1,load_req=0;
    wire uart_tx,load_complete,load_error,io_mem_req,io_mem_we;
    wire [31:0] io_mem_addr,io_mem_wdata;wire [3:0] io_mem_be;
    logic io_mem_gnt,io_mem_rvalid=0,io_mem_error=0;
    logic [31:0] io_mem_rdata=0;
    wire bridge_ready,bridge_busy,bridge_error;
    image_bridge_autoload #(.CLOCK_HZ(100000000),.BAUD(12500000),
        .TIMEOUT_CYCLES(80),.SRAM_SIZE(4096),.DESCRIPTOR_MODE(1)) dut(.*);
    logic [31:0] descriptor[0:4];
    integer test=0,ticks=0,delay=0,accepted=0;
    logic pending=0;logic [31:0] address;
    always_comb io_mem_gnt=io_mem_req && test!=6 && !pending && ticks%5==0;
    always @(posedge clk) begin
        ticks<=ticks+1;io_mem_rvalid<=0;io_mem_error<=0;
        if(!rst_n) pending<=0;
        else begin
            if(io_mem_req && (io_mem_we || io_mem_be!=0)) $fatal(1,"descriptor read used write/byte enables");
            if(io_mem_req && io_mem_gnt) begin
                pending<=1;address<=io_mem_addr;delay<=3;accepted<=accepted+1;
            end
            if(pending && test!=7) begin
                if(delay==0) begin
                    pending<=0;io_mem_rvalid<=1;
                    io_mem_rdata<=descriptor[(address-'h60)/4];io_mem_error<=test==8;
                end else delay<=delay-1;
            end
        end
    end
    task run_case(input integer kind,input integer code,input integer reads);
        @(negedge clk);rst_n=0;load_req=0;test=kind;accepted=0;
        descriptor[0]=32'h31444c49;descriptor[1]=0;descriptor[2]='h200;
        descriptor[3]=17;descriptor[4]=0;
        case(kind)
            0:descriptor[0]=0;
            1:descriptor[3]=0;
            2:descriptor[2]='h40;
            3:descriptor[2]='h60;
            4:descriptor[2]='hff8;
            5:descriptor[1]='hfffffff8;
            default:;
        endcase
        repeat(4) @(negedge clk);rst_n=1;load_req=1;
        for(integer i=0;i<500;i++) begin
            @(negedge clk);
            if(load_complete) break;
        end
        if(!load_complete || !load_error || !bridge_error || dut.error_code!=code || accepted!=reads)
            $fatal(1,"descriptor rejection kind=%d code=%d expected=%d reads=%d",kind,dut.error_code,code,accepted);
        repeat(4) begin @(negedge clk);if(!load_complete) $fatal(1,"completion not held");end
        load_req=0;repeat(4) @(negedge clk);
        if(load_complete || io_mem_req || bridge_ready || !bridge_error) $fatal(1,"fault did not lock until reset");
        $display("PASS descriptor_rejection kind=%d code=%d",kind,code);
    endtask
    initial begin
        run_case(0,13,1);run_case(1,1,5);run_case(2,1,5);run_case(3,1,5);
        run_case(4,1,5);run_case(5,1,5);run_case(6,11,0);run_case(7,11,1);run_case(8,12,1);
        $display("PASS tb_image_load_descriptor: invalid magic/length/regions/overflow, stalls, timeout, memory error, held completion and reset recovery");$finish;
    end
endmodule
