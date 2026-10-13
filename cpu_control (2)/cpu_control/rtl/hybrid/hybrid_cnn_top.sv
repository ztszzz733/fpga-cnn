// Both actual accelerators share DATASRAM; no arithmetic model in this wrapper.
module hybrid_cnn_top #(
    parameter logic [31:0] MMIO_BASE=32'h40000000,SRAM_BASE=0,SRAM_SIZE=32'h40000
)(
    input logic clk,rst_n,
    input logic [31:0] mmio_addr,mmio_wdata,input logic mmio_re,mmio_we,
    output wire [31:0] mmio_rdata,output wire mmio_ready,
    output wire [10:0] cnn_valid,cnn_write,cnn_byte,
    output wire [351:0] cnn_addr,cnn_wdata,
    input wire [10:0] cnn_ready,cnn_response,input wire [351:0] cnn_rdata,
    input logic cnn_mem_fault,output wire cnn_cancel,
    output wire irq,fault,
    output wire [1:0] config_state,output wire [2:0] read_state,write_state,
    output wire [31:0] read_beats,write_beats
);
    wire [31:0] target_addr,target_wdata,target_rdata,nv_rdata,vec_rdata;
    wire target_re,target_we,target_ready,nv_ready,vec_ready;
    wire cmd_busy,cmd_done,cmd_error;
    wire [31:0] transactions;
    wire vec_select=target_addr>=MMIO_BASE+32'h40000;
    wire nv_irq,nv_fault,nv_cancel,vec_busy,vec_done,vec_fault;
    wire [31:0] vec_code,vec_cycles,vec_jobs,vec_reads,vec_writes,vec_stalls,vec_pending;
    wire [2:0] vec_state;
    wire [10:0] nv_valid,nv_write,nv_byte;
    wire [351:0] nv_addr,nv_wdata;
    assign target_rdata=vec_select ? vec_rdata : nv_rdata;
    assign target_ready=vec_select ? vec_ready : nv_ready;
    assign irq=nv_irq || vec_done;
    assign fault=nv_fault || vec_fault;
    assign cnn_cancel=nv_cancel || vec_fault;
    assign cnn_valid[1:0]=nv_valid[1:0];
    assign cnn_write[1:0]=nv_write[1:0];
    assign cnn_byte[1:0]=nv_byte[1:0];
    assign cnn_addr[63:0]=nv_addr[63:0];
    assign cnn_wdata[63:0]=nv_wdata[63:0];
    assign cnn_valid[10:3]=0;assign cnn_write[10:3]=0;assign cnn_byte[10:3]=0;
    assign cnn_addr[351:96]=0;assign cnn_wdata[351:96]=0;
    cnn_command_port #(.BASE(MMIO_BASE)) command_port (
        .clk,.rst_n,.mmio_addr,.mmio_wdata,.mmio_re,.mmio_we,.mmio_rdata,.mmio_ready,
        .target_addr,.target_wdata,.target_re,.target_we,.target_rdata,.target_ready,
        .busy(cmd_busy),.done(cmd_done),.error(cmd_error),.transactions
    );
    nvdla_cnn_top #(.MMIO_BASE(MMIO_BASE),.SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE)) nvdla (
        .clk,.rst_n,.mmio_addr(target_addr),.mmio_wdata(target_wdata),
        .mmio_re(target_re&&!vec_select),.mmio_we(target_we&&!vec_select),
        .mmio_rdata(nv_rdata),.mmio_ready(nv_ready),
        .cnn_valid(nv_valid),.cnn_write(nv_write),.cnn_byte(nv_byte),
        .cnn_addr(nv_addr),.cnn_wdata(nv_wdata),.cnn_ready,.cnn_response,.cnn_rdata,
        .cnn_mem_fault,.cnn_cancel(nv_cancel),.irq(nv_irq),.fault(nv_fault),
        .config_state,.read_state,.write_state,.read_beats,.write_beats
    );
    vicuna_programmable #(.BASE(MMIO_BASE+32'h40000),.SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE)) vector_unit (
        .clk,.rst_n,.cfg_addr(target_addr),.cfg_wdata(target_wdata),
        .cfg_re(target_re&&vec_select),.cfg_we(target_we&&vec_select),
        .cfg_rdata(vec_rdata),.cfg_ready(vec_ready),
        .mem_valid(cnn_valid[2]),.mem_write(cnn_write[2]),.mem_byte(cnn_byte[2]),
        .mem_addr(cnn_addr[95:64]),.mem_wdata(cnn_wdata[95:64]),
        .mem_ready(cnn_ready[2]),.mem_response(cnn_response[2]),.mem_rdata(cnn_rdata[95:64]),
        .mem_fault(cnn_mem_fault),.busy(vec_busy),.done(vec_done),.fault(vec_fault),
        .result_code(vec_code),.cycles(vec_cycles),.jobs(vec_jobs),
        .memory_state(vec_state),.reads(vec_reads),.writes(vec_writes),
        .stalls(vec_stalls),.pending_registers(vec_pending)
    );
endmodule
