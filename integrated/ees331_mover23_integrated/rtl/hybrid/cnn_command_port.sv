// Zero-wait RV32I mailbox -> variable-latency CNN configuration bus.
// Software writes ADDR, DATA, CMD, polls STATUS, then reads RESULT.
module cnn_command_port #(
    parameter logic [31:0] BASE=32'h40000000,
    parameter integer TIMEOUT=100000
)(
    input logic clk,rst_n,
    input logic [31:0] mmio_addr,mmio_wdata,
    input logic mmio_re,mmio_we,
    output logic [31:0] mmio_rdata,output wire mmio_ready,
    output logic [31:0] target_addr,target_wdata,
    output wire target_re,target_we,
    input logic [31:0] target_rdata,input logic target_ready,
    output wire busy,output logic done,error,
    output logic [31:0] transactions
);
    logic active,write_cmd;
    logic [31:0] address_q,data_q,result_q,timer;
    assign busy=active;
    assign mmio_ready=1'b1; // Matches the unchanged main CPU contract.
    assign target_re=active&&!write_cmd;
    assign target_we=active&&write_cmd;
    always_comb begin
        case(mmio_addr-BASE)
            0: mmio_rdata=address_q;
            4: mmio_rdata=data_q;
            8: mmio_rdata=0;
            12: mmio_rdata={29'b0,error,done,active};
            16: mmio_rdata=result_q;
            20: mmio_rdata=transactions;
            default: mmio_rdata=32'hdeadbad0;
        endcase
    end
    always_ff @(posedge clk) begin
        if(!rst_n) begin
            active<=0;write_cmd<=0;done<=0;error<=0;timer<=0;
            address_q<=0;data_q<=0;result_q<=0;transactions<=0;
            target_addr<=0;target_wdata<=0;
        end else begin
            if(active) begin
                timer<=timer+1;
                if(target_ready) begin
                    active<=0;done<=1;result_q<=target_rdata;
                    transactions<=transactions+1;
                end else if(timer==TIMEOUT-1) begin
                    active<=0;done<=1;error<=1;result_q<=32'hdead0001;
                end
            end
            if(mmio_we) case(mmio_addr-BASE)
                0: if(!active) address_q<=mmio_wdata; else error<=1;
                4: if(!active) data_q<=mmio_wdata; else error<=1;
                8: begin
                    if(active) error<=1;
                    else if((mmio_wdata!=1 && mmio_wdata!=2) || address_q[1:0]!=0 ||
                        address_q<BASE || address_q>=BASE+32'h45000) begin
                        done<=1;error<=1;result_q<=32'hdead0002;
                    end else begin
                        active<=1;done<=0;error<=0;timer<=0;
                        write_cmd<=mmio_wdata==1;
                        target_addr<=address_q;target_wdata<=data_q;
                    end
                end
                default: ;
            endcase
        end
    end
endmodule
