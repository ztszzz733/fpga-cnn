// Six peers, with an isolated active UART loader and three direct CPU handshake wires.
module face_soc_neureka_top #(
    parameter integer BANKS=4, ENABLE_OVERLAP=1,
    parameter integer CLOCK_HZ = 50_000_000,
    parameter integer BAUD = 115200,
    parameter integer UART_TIMEOUT_CYCLES = CLOCK_HZ,
    parameter integer CHUNK_BYTES = 64,
    parameter logic [31:0] LOAD_CTRL_ADDR = 32'h40,
    parameter logic [31:0] SOURCE_BASE = 0,
    parameter logic [31:0] LOAD_BASE = 32'h100,
    parameter integer LOAD_BYTES = 256,
    parameter logic [31:0] EXPECTED_CRC32 = 32'hfe679cc9,
    parameter logic [31:0] RESET_PC = 32'h0000_0000,
    parameter logic [31:0] IMEM_BASE = 32'h0000_0000,
    parameter logic [31:0] IMEM_SIZE = 32'h0001_0000,
    parameter string IMEM_INIT_FILE = "",
    parameter logic [31:0] SRAM_BASE = 32'h0000_0000,
    parameter logic [31:0] SRAM_SIZE = 32'h0004_0000,
    parameter logic [31:0] CNN_MMIO_BASE = 32'h4000_0000
) (
    input logic sys_clk, rst_n_in, uart_rx,
    output wire uart_tx, led_ready, led_busy, led_error
);
    wire clk, rst_n;
    wire load_req, load_complete, load_error;
    wire io_mem_req, io_mem_we, io_mem_gnt, io_mem_rvalid, io_mem_error;
    wire [31:0] io_mem_addr, io_mem_wdata, io_mem_rdata;
    wire [3:0] io_mem_be;
    wire cnn_mem_fault, bridge_ready, bridge_busy, bridge_error;
    assign led_ready = bridge_ready && !cnn_mem_fault;
    assign led_busy = bridge_busy;
    assign led_error = bridge_error || cnn_mem_fault;
    clock_unit u_clock_unit (.*);
    image_bridge_autoload #(.CLOCK_HZ(CLOCK_HZ), .BAUD(BAUD),
        .TIMEOUT_CYCLES(UART_TIMEOUT_CYCLES), .CHUNK_BYTES(CHUNK_BYTES),
        .LOAD_CTRL_ADDR(LOAD_CTRL_ADDR), .SOURCE_BASE(SOURCE_BASE),
        .LOAD_BASE(LOAD_BASE), .LOAD_BYTES(LOAD_BYTES), .EXPECTED_CRC32(EXPECTED_CRC32),
        .SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE)) u_image_bridge (.*);
    logic [31:0] imem_addr, imem_rdata, dmem_addr, dmem_wdata, dmem_rdata;
    logic imem_re, dmem_re, dmem_we;
    logic [3:0] dmem_wstrb;
    logic [31:0] cnn_mmio_addr, cnn_mmio_wdata, cnn_mmio_rdata;
    logic cnn_mmio_re, cnn_mmio_we, cnn_mmio_ready;
    wire [10:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response;
    wire [351:0] cnn_addr,cnn_wdata,cnn_rdata;
    wire cnn_cancel;
    wire cnn_status_busy,cnn_status_done,cnn_status_error;

    // Passive first-level observer. Six parallel state machines, no seventh
    // module and no control feedback into the functional datapaths.
    typedef enum logic [1:0] {ST_RESET=2'd0,ST_IDLE=2'd1,ST_WORK=2'd2,ST_FAULT=2'd3} module_state_t;
    module_state_t cpu_state,cnn_state,sram_state,imem_state,bridge_state,clock_state;
    wire [11:0] soc_module_state={clock_state,bridge_state,imem_state,sram_state,cnn_state,cpu_state};
    wire [5:0] soc_active={clock_state==ST_WORK,bridge_state==ST_WORK,imem_state==ST_WORK,
                          sram_state==ST_WORK,cnn_state==ST_WORK,cpu_state==ST_WORK};
    wire [5:0] soc_fault={clock_state==ST_FAULT,bridge_state==ST_FAULT,imem_state==ST_FAULT,
                         sram_state==ST_FAULT,cnn_state==ST_FAULT,cpu_state==ST_FAULT};
    // State describes activity sampled at the last rising edge. WORK is
    // interface/transaction activity, not an instruction-retirement counter.
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            cpu_state<=ST_RESET;cnn_state<=ST_RESET;sram_state<=ST_RESET;
            imem_state<=ST_RESET;bridge_state<=ST_RESET;
        end else begin
            cpu_state<=(imem_re || dmem_re || dmem_we || cnn_mmio_re || cnn_mmio_we || load_req) ? ST_WORK : ST_IDLE;
            imem_state<=imem_re ? ST_WORK : ST_IDLE;
            sram_state<=cnn_mem_fault ? ST_FAULT :
                (dmem_re || dmem_we || (|cnn_valid) || (|cnn_response) || io_mem_req || io_mem_rvalid) ? ST_WORK : ST_IDLE;
            bridge_state<=bridge_error ? ST_FAULT : bridge_busy ? ST_WORK : ST_IDLE;
            if(cnn_cancel) cnn_state<=ST_IDLE;
            else if(cnn_mem_fault || cnn_status_error || cnn_state==ST_FAULT) cnn_state<=ST_FAULT;
            else cnn_state<=cnn_status_busy ? ST_WORK : ST_IDLE;
        end
    end
    // CLOCK IDLE means reset release is in progress; WORK is reset released.
    // This is not a PLL-lock or clock-frequency detector.
    always_ff @(posedge sys_clk or negedge rst_n_in)
        if(!rst_n_in) clock_state<=ST_RESET;
        else clock_state<=rst_n ? ST_WORK : ST_IDLE;

    cpu_core_autoload #(.RESET_PC(RESET_PC), .SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE),
        .CNN_MMIO_BASE(CNN_MMIO_BASE), .LOAD_CTRL_ADDR(LOAD_CTRL_ADDR)) u_cpu_core (
        .mmio_addr(cnn_mmio_addr), .mmio_wdata(cnn_mmio_wdata),
        .mmio_re(cnn_mmio_re), .mmio_we(cnn_mmio_we),
        .mmio_rdata(cnn_mmio_rdata), .mmio_ready(cnn_mmio_ready), .*
    );
    imem_rom #(.IMEM_BASE(IMEM_BASE), .IMEM_SIZE(IMEM_SIZE),
        .INIT_FILE(IMEM_INIT_FILE)) u_imem (.*);
    datasram_banked #(.SRAM_BASE(SRAM_BASE), .SRAM_SIZE(SRAM_SIZE), .BANKS(BANKS)) u_datasram (.*);
    mobilefacenet_neureka_top #(.BASE_ADDR(CNN_MMIO_BASE), .ENABLE_OVERLAP(ENABLE_OVERLAP)) u_cnn (
        .clk(clk), .rst_n(rst_n),
        .mmio_addr(cnn_mmio_addr), .mmio_wdata(cnn_mmio_wdata),
        .mmio_re(cnn_mmio_re), .mmio_we(cnn_mmio_we),
        .mmio_rdata(cnn_mmio_rdata), .mmio_ready(cnn_mmio_ready),
        .cnn_valid(cnn_valid),.cnn_write(cnn_write),.cnn_byte(cnn_byte),
        .cnn_addr(cnn_addr),.cnn_wdata(cnn_wdata),.cnn_ready(cnn_ready),
        .cnn_response(cnn_response),.cnn_rdata(cnn_rdata),.cnn_cancel(cnn_cancel),
        .status_busy(cnn_status_busy),.status_done(cnn_status_done),.status_error(cnn_status_error)
    );
endmodule
