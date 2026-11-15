// Original UART primitives, namespaced for the isolated autoload file list.
module autoload_uart_rx #(parameter integer DIVISOR=434)(
    input logic clk,rst_n,rx, output logic [7:0] data,
    output logic valid,error
);
    (* ASYNC_REG="TRUE" *) logic [1:0] sync_rx;
    logic [7:0] shift;
    integer phase,ticks,bit_index;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sync_rx<=2'b11; phase<=0; ticks<=0; bit_index<=0;
            shift<=0; data<=0; valid<=0; error<=0;
        end else begin
            sync_rx<={sync_rx[0],rx}; valid<=0; error<=0;
            case (phase)
                0: if (!sync_rx[1]) begin ticks<=DIVISOR/2-1; phase<=1; end
                1: if (ticks!=0) ticks<=ticks-1;
                   else if (!sync_rx[1]) begin ticks<=DIVISOR-1; bit_index<=0; phase<=2; end
                   else phase<=0;
                2: if (ticks!=0) ticks<=ticks-1;
                   else begin
                       shift[bit_index]<=sync_rx[1]; ticks<=DIVISOR-1;
                       if (bit_index==7) phase<=3; else bit_index<=bit_index+1;
                   end
                3: if (ticks!=0) ticks<=ticks-1;
                   else if (sync_rx[1]) begin data<=shift; valid<=1; phase<=0; end
                   else begin error<=1; phase<=4; end
                4: if (sync_rx[1]) phase<=0;
                default: phase<=0;
            endcase
        end
    end
endmodule

module autoload_uart_tx #(parameter integer DIVISOR=434)(
    input logic clk,rst_n,valid, input logic [7:0] data,
    output wire ready,tx
);
    logic busy;
    logic [9:0] shift;
    integer ticks,bit_index;
    assign ready=!busy;
    assign tx=busy ? shift[0] : 1'b1;
    always_ff @(posedge clk) begin
        if (!rst_n) begin busy<=0; shift<=10'h3ff; ticks<=0; bit_index<=0; end
        else if (!busy) begin
            if (valid) begin
                busy<=1; shift<={1'b1,data,1'b0}; ticks<=DIVISOR-1; bit_index<=0;
            end
        end else if (ticks!=0) ticks<=ticks-1;
        else if (bit_index==9) busy<=0;
        else begin shift<={1'b1,shift[9:1]}; ticks<=DIVISOR-1; bit_index<=bit_index+1; end
    end
endmodule
