// One image-bridge module at SoC level: parallel PHY/FIFOs + unchanged loader ABI.
module image_bridge_fx8 #(
    parameter integer CLOCK_HZ=100_000_000,TIMEOUT_CYCLES=CLOCK_HZ,CHUNK_BYTES=256,
    parameter logic [31:0] SRAM_BASE=0,SRAM_SIZE=32'h40000,LOAD_CTRL_ADDR=32'h40,
    parameter logic [31:0] SOURCE_BASE=0,LOAD_BASE=32'h100,
    parameter integer LOAD_BYTES=256,
    parameter logic [31:0] EXPECTED_CRC32=32'hfe679cc9,
    parameter bit DESCRIPTOR_MODE=1,
    parameter logic [31:0] DESCRIPTOR_ADDR=SRAM_BASE+32'h60
)(
    input wire clk,rst_n,
    output wire fx8_clk,fx8_reset_n,
    input wire [7:0] fx8_rx_data,
    input wire fx8_rx_valid,fx8_tx_ready,
    output wire fx8_rx_ready,fx8_tx_valid,
    output wire [7:0] fx8_tx_data,
    input wire load_req,
    output wire load_complete,load_error,
    output wire io_mem_req,io_mem_we,
    output wire [31:0] io_mem_addr,io_mem_wdata,
    output wire [3:0] io_mem_be,
    input wire io_mem_gnt,io_mem_rvalid,io_mem_error,
    input wire [31:0] io_mem_rdata,
    output wire bridge_ready,bridge_busy,bridge_error
);
    wire [7:0] rx_data,tx_data;
    wire rx_valid,rx_ready,tx_valid,tx_ready;
    fx8_link u_link(.fault(bridge_error),.*);
    image_load_stream #(.CLOCK_HZ(CLOCK_HZ),.TIMEOUT_CYCLES(TIMEOUT_CYCLES),.CHUNK_BYTES(CHUNK_BYTES),
        .SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE),.LOAD_CTRL_ADDR(LOAD_CTRL_ADDR),
        .SOURCE_BASE(SOURCE_BASE),.LOAD_BASE(LOAD_BASE),.LOAD_BYTES(LOAD_BYTES),.EXPECTED_CRC32(EXPECTED_CRC32),
        .DESCRIPTOR_MODE(DESCRIPTOR_MODE),.DESCRIPTOR_ADDR(DESCRIPTOR_ADDR)) u_loader(.*);
endmodule
