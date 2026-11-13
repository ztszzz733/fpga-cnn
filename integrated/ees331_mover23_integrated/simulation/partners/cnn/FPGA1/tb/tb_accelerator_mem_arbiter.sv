`timescale 1ns/1ps
module tb_accelerator_mem_arbiter;
    reg clk=0;always #5 clk=~clk;reg rst_n=0,clear=0;
    wire [2:0] ready,response;reg [2:0] valid=0;
    wire cv,cw,cb,cr,rv,idle,mem_idle;wire [31:0] ca,cd,data,ma,md,mr;wire rd,wr,mready;
    wire [1:0] owner;integer accepted[0:2],returned[0:2],i,total=0,last=-1;
    accelerator_mem_arbiter dut(clk,rst_n,clear,valid,3'b000,3'b000,{32'd8,32'd4,32'd0},96'd0,
        ready,response,cv,cw,cb,ca,cd,cr,rv,idle,owner);
    accelerator_mem_if mif(clk,rst_n,clear,cv,cr,cw,cb,ca,cd,rv,data,mem_idle,ma,md,rd,wr,mr,mready);
    model_data_ram #(64,5) ram(clk,rst_n,ma,md,rd,wr,mr,mready);
    always @(negedge clk) if(rst_n) for(integer j=0;j<3;j=j+1)
        valid[j]=accepted[j]<12 && accepted[j]==returned[j];
    always @(posedge clk) if(rst_n) begin
        if((response & (response-1'b1))!=0) $fatal(1,"response delivered twice");
        for(integer j=0;j<3;j=j+1) begin
            if(valid[j] && ready[j]) begin
                if(accepted[j]!=returned[j]) $fatal(1,"client already outstanding");
                if(j!=(last+1)%3) $fatal(1,"round-robin fairness");
                accepted[j]=accepted[j]+1;last=j;
            end
            if(response[j]) begin
                if(accepted[j]!=returned[j]+1 || data!==32'h11220000+j || owner!=j) $fatal(1,"wrong response owner/data");
                returned[j]=returned[j]+1;total=total+1;
            end
        end
    end
    initial begin
        for(i=0;i<3;i=i+1) begin
            accepted[i]=0;returned[i]=0;ram.bytes[i*4]=i;ram.bytes[i*4+1]=0;ram.bytes[i*4+2]='h22;ram.bytes[i*4+3]='h11;
        end
        repeat(2) @(negedge clk);rst_n=1;
        while(total<36) @(negedge clk);
        if(ram.reads!=36 || ram.writes!=0) $fatal(1,"transaction count");
        $display("PASS tb_accelerator_mem_arbiter (36 stalled requests, fair grants, response ownership)");$finish;
    end
    initial begin #100000;$fatal(1,"timeout");end
endmodule
