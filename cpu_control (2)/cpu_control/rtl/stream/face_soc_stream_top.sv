// Six top-level modules. Stream buffers and line/window logic live inside
// IMAGE_BRIDGE and CNN; the previous general-purpose SoC remains separate.
module face_soc_stream_top #(
    parameter integer WIDTH=524,HEIGHT=524,FRAMES=6,CHUNK=1024,
    parameter integer CLOCK_HZ=100000000,BAUD=25000000,UART_TIMEOUT=10000,
    parameter logic [31:0] SRAM_SIZE=32'h100000,
    parameter string IMEM_INIT_FILE="program.mem"
)(
    input wire sys_clk,rst_n_in,uart_rx,
    output wire uart_tx,led_ready,led_busy,led_error
);
    wire clk,rst_n;
    wire [31:0] imem_addr,imem_rdata,dmem_addr,dmem_wdata,dmem_rdata;
    wire imem_re,dmem_re,dmem_we;wire [3:0] dmem_wstrb;
    wire [31:0] cnn_mmio_addr,cnn_mmio_wdata,cnn_mmio_rdata;
    wire cnn_mmio_re,cnn_mmio_we,cnn_mmio_ready;
    wire load_req,load_complete,load_error,bridge_ready,bridge_busy,bridge_error;
    wire pixel_valid,pixel_ready,pixel_sof,pixel_eof;wire [7:0] pixel_data;wire [31:0] pixel_frame;
    wire rx_receiving;wire [31:0] packets_checked;
    wire [10:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response;
    wire [351:0] cnn_addr,cnn_wdata,cnn_rdata;
    wire cnn_cancel,cnn_mem_fault,cnn_status_busy,cnn_status_done,cnn_status_error;
    wire compute_fire,frame_done;wire [31:0] frames_done,pixels_consumed;
    clock_unit u_clock_unit(.*);
    cpu_core_autoload #(.SRAM_SIZE(SRAM_SIZE)) u_cpu_core(
        .mmio_addr(cnn_mmio_addr),.mmio_wdata(cnn_mmio_wdata),.mmio_rdata(cnn_mmio_rdata),
        .mmio_re(cnn_mmio_re),.mmio_we(cnn_mmio_we),.mmio_ready(cnn_mmio_ready),.*);
    imem_rom #(.IMEM_SIZE(4096),.INIT_FILE(IMEM_INIT_FILE)) u_imem(.*);
    image_bridge_stream #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.FRAMES(FRAMES),.CHUNK(CHUNK),
        .CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD),.TIMEOUT(UART_TIMEOUT)) u_image_bridge(.*);
    cnn_stream_features #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.FRAMES(FRAMES),.SRAM_SIZE(SRAM_SIZE)) u_cnn(
        .mmio_addr(cnn_mmio_addr),.mmio_wdata(cnn_mmio_wdata),.mmio_rdata(cnn_mmio_rdata),
        .mmio_re(cnn_mmio_re),.mmio_we(cnn_mmio_we),.mmio_ready(cnn_mmio_ready),.stream_error(bridge_error),.*);
    datasram_banked #(.SRAM_SIZE(SRAM_SIZE)) u_datasram(
        .io_mem_req(1'b0),.io_mem_we(1'b0),.io_mem_addr(32'd0),.io_mem_wdata(32'd0),.io_mem_be(4'd0),
        .io_mem_gnt(),.io_mem_rvalid(),.io_mem_rdata(),.io_mem_error(),.*);
    assign led_ready=bridge_ready && !cnn_mem_fault;
    assign led_busy=bridge_busy || cnn_status_busy;
    assign led_error=bridge_error || cnn_mem_fault || cnn_status_error;
    typedef enum logic [1:0] {RESET=0,IDLE=1,WORK=2,FAULT=3} state_t;
    state_t cpu_state,cnn_state,sram_state,imem_state,bridge_state,clock_state;
    wire [11:0] soc_module_state={clock_state,bridge_state,imem_state,sram_state,cnn_state,cpu_state};
    wire [5:0] soc_active={clock_state==WORK,bridge_state==WORK,imem_state==WORK,sram_state==WORK,cnn_state==WORK,cpu_state==WORK};
    wire [5:0] soc_fault={clock_state==FAULT,bridge_state==FAULT,imem_state==FAULT,sram_state==FAULT,cnn_state==FAULT,cpu_state==FAULT};
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin cpu_state<=RESET;cnn_state<=RESET;sram_state<=RESET;imem_state<=RESET;bridge_state<=RESET;end
        else begin
            cpu_state<=imem_re || dmem_re || dmem_we || cnn_mmio_re || cnn_mmio_we || load_req ? WORK : IDLE;
            imem_state<=imem_re ? WORK:IDLE;
            sram_state<=cnn_mem_fault ? FAULT : dmem_re || dmem_we || |cnn_valid || |cnn_response ? WORK:IDLE;
            bridge_state<=bridge_error ? FAULT : bridge_busy ? WORK:IDLE;
            if(cnn_status_error || cnn_mem_fault || bridge_error) cnn_state<=FAULT;
            else if(cnn_cancel) cnn_state<=IDLE;
            else if(cnn_state!=FAULT) cnn_state<=cnn_status_busy ? WORK:IDLE;
        end
    end
    always_ff @(posedge sys_clk or negedge rst_n_in)
        if(!rst_n_in) clock_state<=RESET;else clock_state<=rst_n ? WORK:IDLE;
endmodule
