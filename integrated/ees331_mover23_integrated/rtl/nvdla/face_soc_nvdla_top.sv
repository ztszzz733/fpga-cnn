// Alternative six-module SoC wiring. Requires NVDLA register-programming firmware;
// the old NEureka task-descriptor firmware is not compatible with this entry.
module face_soc_nvdla_top #(
    parameter integer BANKS=4,CLOCK_HZ=50_000_000,BAUD=115200,
    parameter integer UART_TIMEOUT_CYCLES=CLOCK_HZ,CHUNK_BYTES=64,
    parameter logic [31:0] LOAD_CTRL_ADDR=32'h40,SOURCE_BASE=0,LOAD_BASE=32'h100,
    parameter integer LOAD_BYTES=256,
    parameter logic [31:0] EXPECTED_CRC32=32'hfe679cc9,RESET_PC=0,IMEM_BASE=0,IMEM_SIZE=32'h10000,
    parameter string IMEM_INIT_FILE="",
    parameter logic [31:0] SRAM_BASE=0,SRAM_SIZE=32'h40000,CNN_MMIO_BASE=32'h40000000
)(
    input logic sys_clk,rst_n_in,uart_rx,
    output wire uart_tx,led_ready,led_busy,led_error
);
    wire clk,rst_n,load_req,load_complete,load_error;
    wire io_mem_req,io_mem_we,io_mem_gnt,io_mem_rvalid,io_mem_error;
    wire [31:0] io_mem_addr,io_mem_wdata,io_mem_rdata;
    wire [3:0] io_mem_be;
    wire bridge_ready,bridge_busy,bridge_error,cnn_mem_fault,cnn_cancel,cnn_fault,cnn_irq;
    wire [31:0] imem_addr,imem_rdata,dmem_addr,dmem_wdata,dmem_rdata;
    wire imem_re,dmem_re,dmem_we;
    wire [3:0] dmem_wstrb;
    wire [31:0] mmio_addr,mmio_wdata,mmio_rdata;
    wire mmio_re,mmio_we,mmio_ready;
    wire [10:0] cnn_valid,cnn_write,cnn_byte,cnn_ready,cnn_response;
    wire [351:0] cnn_addr,cnn_wdata,cnn_rdata;
    wire [1:0] config_state;
    wire [2:0] read_state,write_state;
    wire [31:0] read_beats,write_beats;
    assign led_ready=bridge_ready&&!cnn_fault;
    assign led_busy=bridge_busy;
    assign led_error=bridge_error||cnn_fault;
    clock_unit u_clock_unit (.*);
    image_bridge_autoload #(.CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD),.TIMEOUT_CYCLES(UART_TIMEOUT_CYCLES),
        .CHUNK_BYTES(CHUNK_BYTES),.LOAD_CTRL_ADDR(LOAD_CTRL_ADDR),.SOURCE_BASE(SOURCE_BASE),
        .LOAD_BASE(LOAD_BASE),.LOAD_BYTES(LOAD_BYTES),.EXPECTED_CRC32(EXPECTED_CRC32),
        .SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE)) u_image_bridge (.*);
    // Native NVDLA CSB map spans more than the old 4 KB CNN aperture.
    cpu_core_autoload #(.RESET_PC(RESET_PC),.SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE),
        .CNN_MMIO_BASE(CNN_MMIO_BASE),.CNN_MMIO_SIZE(32'h40000),.LOAD_CTRL_ADDR(LOAD_CTRL_ADDR)) u_cpu_core (.*);
    imem_rom #(.IMEM_BASE(IMEM_BASE),.IMEM_SIZE(IMEM_SIZE),.INIT_FILE(IMEM_INIT_FILE)) u_imem (.*);
    datasram_banked #(.SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE),.BANKS(BANKS)) u_datasram (.*);
    nvdla_cnn_top #(.MMIO_BASE(CNN_MMIO_BASE),.SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE)) u_cnn (
        .irq(cnn_irq),.fault(cnn_fault),.*
    );
endmodule
