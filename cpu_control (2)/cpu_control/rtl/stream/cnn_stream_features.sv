// Fixed two-filter CNN front end: valid Sobel X/Y -> abs/4 -> 2x2 maxpool.
// Constant coefficients synthesize to adds/shifts; no full-frame input buffer.
module cnn_stream_features #(
    parameter integer WIDTH=524,HEIGHT=524,FRAMES=6,
    parameter logic [31:0] BASE_ADDR=32'h40000000,SRAM_SIZE=32'h100000
)(
    input wire clk,rst_n,
    input wire [31:0] mmio_addr,mmio_wdata,input wire mmio_re,mmio_we,
    output logic [31:0] mmio_rdata,output wire mmio_ready,
    input wire pixel_valid,output wire pixel_ready,input wire [7:0] pixel_data,
    input wire pixel_sof,pixel_eof,input wire [31:0] pixel_frame,
    input wire stream_error,cnn_mem_fault,
    output logic [10:0] cnn_valid,cnn_write,cnn_byte,
    output logic [351:0] cnn_addr,cnn_wdata,
    input wire [10:0] cnn_ready,cnn_response,input wire [351:0] cnn_rdata,
    output wire cnn_cancel,
    output logic cnn_status_busy,cnn_status_done,cnn_status_error,
    output logic compute_fire,frame_done,output logic [31:0] frames_done,
    output logic [31:0] pixels_consumed
);
    localparam integer OW=(WIDTH-2)/2,OH=(HEIGHT-2)/2,FRAME_BYTES=OW*OH*2;
    logic [7:0] line1[0:WIDTH-1],line2[0:WIDTH-1];
    logic [7:0] pool_x[0:WIDTH-3],pool_y[0:WIDTH-3];
    logic [7:0] t0,t1,m0,m1,b0,b1,hx,hy;
    logic [1:0] pending,waiting;
    logic [31:0] write_addr;
    logic [7:0] wx,wy;
    logic eof_pending,done_sticky,error_sticky;
    logic [31:0] output_base;
    integer row,col;
    wire selected=mmio_addr>=BASE_ADDR && mmio_addr<BASE_ADDR+32;
    assign mmio_ready=selected && (mmio_re || mmio_we);
    wire start=mmio_we && mmio_ready && mmio_addr==BASE_ADDR && mmio_wdata[0];
    assign cnn_cancel=(mmio_we && mmio_ready && mmio_addr==BASE_ADDR && mmio_wdata[1]) || stream_error;
    assign pixel_ready=cnn_status_busy && !error_sticky && !stream_error && !cnn_mem_fault &&
                       pending==0 && waiting==0 && !eof_pending;
    function automatic [7:0] vmax(input [7:0] a,b);return a>b ? a:b;endfunction
    always_comb begin
        mmio_rdata=0;
        case(mmio_addr-BASE_ADDR)
        4:mmio_rdata={29'd0,error_sticky,done_sticky,cnn_status_busy};
        8:mmio_rdata=output_base;
        12:mmio_rdata=frames_done;
        16:mmio_rdata=pixels_consumed;
        20:mmio_rdata=FRAME_BYTES;
        24:mmio_rdata={16'(HEIGHT),16'(WIDTH)};
        28:mmio_rdata=FRAMES;
        default:mmio_rdata=0;
        endcase
        cnn_valid=0;cnn_write=0;cnn_byte=0;cnn_addr=0;cnn_wdata=0;
        cnn_valid[1:0]=pending;cnn_write[1:0]=2'b11;cnn_byte[1:0]=2'b11;
        cnn_addr[31:0]=write_addr;cnn_addr[63:32]=write_addr+1;
        cnn_wdata[31:0]={24'd0,wx};cnn_wdata[63:32]={24'd0,wy};
    end
    always_ff @(posedge clk) begin: engine
        integer gx,gy,ox,oy;
        reg [7:0] ax,ay,vx,vy;
        if(!rst_n) begin
            cnn_status_busy<=0;cnn_status_done<=0;cnn_status_error<=0;
            compute_fire<=0;frame_done<=0;frames_done<=0;pixels_consumed<=0;
            pending<=0;waiting<=0;eof_pending<=0;done_sticky<=0;error_sticky<=0;
            output_base<=32'h1000;write_addr<=0;wx<=0;wy<=0;
            row<=0;col<=0;t0<=0;t1<=0;m0<=0;m1<=0;b0<=0;b1<=0;hx<=0;hy<=0;
        end else begin
            cnn_status_done<=0;cnn_status_error<=0;compute_fire<=0;frame_done<=0;
            pending<=pending & ~cnn_ready[1:0];
            waiting<=(waiting | (pending & cnn_ready[1:0])) & ~cnn_response[1:0];
            if(mmio_we && mmio_ready && mmio_addr==BASE_ADDR+8 && !cnn_status_busy) output_base<=mmio_wdata;
            if(start && !cnn_status_busy && !error_sticky) begin
                if(output_base[1:0]!=0 || {1'b0,output_base}+FRAMES*FRAME_BYTES>SRAM_SIZE) begin
                    error_sticky<=1;cnn_status_error<=1;
                end else begin
                    cnn_status_busy<=1;done_sticky<=0;frames_done<=0;pixels_consumed<=0;
                    row<=0;col<=0;eof_pending<=0;pending<=0;waiting<=0;
                end
            end
            if(pixel_valid && pixel_ready) begin
                if(pixel_frame!=frames_done || pixel_sof!=(row==0 && col==0) || pixel_eof!=(row==HEIGHT-1 && col==WIDTH-1)) begin
                    error_sticky<=1;cnn_status_error<=1;cnn_status_busy<=0;pending<=0;
                end else begin
                    pixels_consumed<=pixels_consumed+1;
                    line2[col]<=line1[col];line1[col]<=pixel_data;
                    t0<=t1;t1<=line2[col];m0<=m1;m1<=line1[col];b0<=b1;b1<=pixel_data;
                    if(row>=2 && col>=2) begin
                        // Each term is extended before arithmetic. Input pixels are unsigned.
                        gx=-int'(t0)+int'(line2[col])-2*int'(m0)+2*int'(line1[col])-int'(b0)+int'(pixel_data);
                        gy=-int'(t0)-2*int'(t1)-int'(line2[col])+int'(b0)+2*int'(b1)+int'(pixel_data);
                        ax=(gx<0 ? -gx : gx)>>2;ay=(gy<0 ? -gy : gy)>>2;
                        compute_fire<=1;ox=col-2;oy=row-2;
                        if(!oy[0]) begin pool_x[ox]<=ax;pool_y[ox]<=ay;end
                        else begin
                            vx=vmax(ax,pool_x[ox]);vy=vmax(ay,pool_y[ox]);
                            if(!ox[0]) begin hx<=vx;hy<=vy;end
                            else begin
                                wx<=vmax(hx,vx);wy<=vmax(hy,vy);
                                write_addr<=output_base+frames_done*FRAME_BYTES+((oy/2)*OW+ox/2)*2;
                                pending<=2'b11;
                            end
                        end
                    end
                    if(col==WIDTH-1) begin col<=0;row<=row+1;end else col<=col+1;
                    if(pixel_eof) eof_pending<=1;
                end
            end
            if(eof_pending && pending==0 && waiting==0) begin
                eof_pending<=0;frame_done<=1;frames_done<=frames_done+1;row<=0;col<=0;
                if(frames_done==FRAMES-1) begin cnn_status_busy<=0;cnn_status_done<=1;done_sticky<=1;end
            end
            if(cnn_cancel) begin
                pending<=0;waiting<=0;eof_pending<=0;cnn_status_busy<=0;done_sticky<=0;
                error_sticky<=stream_error;cnn_status_error<=stream_error;
            end
            if(cnn_mem_fault) begin pending<=0;waiting<=0;cnn_status_busy<=0;error_sticky<=1;cnn_status_error<=1;end
        end
    end
`ifndef SYNTHESIS
    initial assert(WIDTH>=4 && HEIGHT>=4 && WIDTH%2==0 && HEIGHT%2==0 && FRAMES>0);
`endif
endmodule
