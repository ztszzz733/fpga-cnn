// Drop-in CNN boundary: real NEureka + real programmable Vicuna, two SRAM tiles.
module neureka_pipeline_cnn_top #(
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
    wire [31:0] target_addr,target_wdata,target_rdata,pipe_rdata,vec_rdata;
    wire target_re,target_we,target_ready;
    wire cmd_busy,cmd_done,cmd_error;
    wire [31:0] transactions;
    wire vec_select=target_addr>=MMIO_BASE+32'h40000;
    wire pipe_busy,pipe_done,pipe_fault;
    wire [31:0] pipe_error,pipe_cycles,overlap_cycles,produced,completed;
    wire [3:0] slots;
    wire vec_busy,vec_done,vec_fault,vec_ready;
    wire [31:0] vec_code,vec_cycles,vec_jobs,vec_reads,vec_writes,vec_stalls,vec_pending;
    wire [2:0] vec_state;
    wire vec_we;wire [31:0] vec_addr,vec_wdata;
    logic vec_loaded;
    wire vec_host_we=target_we && vec_select && !pipe_busy && !fault;
    wire [31:0] program_offset=target_addr-(MMIO_BASE+32'h40000);
    always_ff @(posedge clk) begin
        if(!rst_n) vec_loaded<=0;
        else if(vec_host_we && !vec_busy && program_offset>=32'h1000 && program_offset<32'h5000)
            vec_loaded<=1;
    end
    wire conv_start,conv_busy,conv_done,conv_error,core_busy,memory_idle;
    wire [31:0] conv_config_address,conv_cfg_addr,conv_cfg_rdata;
    wire conv_cfg_valid,conv_cfg_ready,conv_cfg_response;
    wire [10:0] valid_raw;
    wire [31:0] conv_output_base,conv_output_capacity;
    logic output_bounds_fault;
    always_comb begin
        output_bounds_fault=0;
        for(int k=0;k<9;k++) if(valid_raw[k] && cnn_write[k]) begin
            if(cnn_addr[k*32+:32]<conv_output_base ||
               {1'b0,cnn_addr[k*32+:32]}+(cnn_byte[k] ? 33'd1 : 33'd4)>
               {1'b0,conv_output_base}+{1'b0,conv_output_capacity}) output_bounds_fault=1;
        end
    end
    assign cnn_valid=valid_raw & {11{!fault}};
    assign fault=pipe_fault || vec_fault || cnn_mem_fault || output_bounds_fault;
    assign cnn_cancel=fault;
    assign irq=pipe_done;
    assign target_rdata=vec_select ? vec_rdata : pipe_rdata;
    // A status read may wait for the five scheduler parameter writes; CPU's
    // outer mailbox remains zero-wait throughout.
    assign target_ready=!(vec_select && target_re && vec_we);
    assign config_state={pipe_fault,pipe_busy};
    assign read_state={1'b0,slots[1:0]};
    assign write_state={1'b0,slots[3:2]};
    // Beat counters retain their literal meaning over all 11 clients.
    logic [31:0] reads_q,writes_q;
    integer nr,nw;
    always_comb begin
        nr=0;nw=0;
        for(int i=0;i<11;i++) if(cnn_valid[i] && cnn_ready[i]) begin
            if(cnn_write[i]) nw=nw+1;else nr=nr+1;
        end
    end
    always_ff @(posedge clk) begin
        if(!rst_n) begin reads_q<=0;writes_q<=0;end
        else begin reads_q<=reads_q+nr;writes_q<=writes_q+nw;end
    end
    assign read_beats=reads_q;assign write_beats=writes_q;
    cnn_command_port #(.BASE(MMIO_BASE)) command_port (
        .clk,.rst_n,.mmio_addr,.mmio_wdata,.mmio_re,.mmio_we,.mmio_rdata,.mmio_ready,
        .target_addr,.target_wdata,.target_re,.target_we,.target_rdata,.target_ready,
        .busy(cmd_busy),.done(cmd_done),.error(cmd_error),.transactions
    );
    neureka_tile_scheduler #(.BASE(MMIO_BASE),.SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE)) scheduler (
        .clk,.rst_n,.cfg_addr(target_addr),.cfg_wdata(target_wdata),.cfg_we(target_we&&!vec_select),
        .host_reject(target_we&&vec_select&&pipe_busy),.cfg_rdata(pipe_rdata),
        .busy(pipe_busy),.done(pipe_done),.fault(pipe_fault),.error_code(pipe_error),
        .mem_valid(valid_raw[9]),.mem_addr(cnn_addr[319:288]),
        .mem_ready(cnn_ready[9]),.mem_response(cnn_response[9]),.mem_rdata(cnn_rdata[319:288]),
        .mem_fault(cnn_mem_fault||output_bounds_fault),.conv_start,.conv_config_address,.conv_busy,.conv_done,.conv_error,
        .conv_cfg_valid,.conv_cfg_addr,.conv_cfg_ready,.conv_cfg_response,.conv_cfg_rdata,
        .vec_we,.vec_addr,.vec_wdata,.vec_busy,.vec_done,.vec_fault,.vec_loaded,
        .vec_idle(vec_state==0 && vec_pending==0),
        .cycles(pipe_cycles),.overlap_cycles,.produced,.completed,.slot_status(slots),
        .conv_output_base,.conv_output_capacity
    );
    assign cnn_write[9]=0;assign cnn_byte[9]=0;assign cnn_wdata[319:288]=0;
    neureka_conv_engine convolution (
        // Bounds faults gate SRAM immediately and latch in the scheduler.
        // Clear from registered faults to avoid a valid -> clear -> valid loop.
        .clk,.rst_n,.clear(pipe_fault||vec_fault||cnn_mem_fault),.start(conv_start),.config_address(conv_config_address),
        .busy(conv_busy),.done(conv_done),.error(conv_error),
        .cfg_valid(conv_cfg_valid),.cfg_addr(conv_cfg_addr),.cfg_ready(conv_cfg_ready),
        .cfg_response(conv_cfg_response),.cfg_rdata(conv_cfg_rdata),
        .valid(valid_raw[8:0]),.write(cnn_write[8:0]),.byte_access(cnn_byte[8:0]),
        .addr(cnn_addr[287:0]),.wdata(cnn_wdata[287:0]),.ready(cnn_ready[8:0]),
        .response(cnn_response[8:0]),.rdata(cnn_rdata[287:0]),.core_busy,.memory_idle
    );
    vicuna_programmable #(.BASE(MMIO_BASE+32'h40000),.SRAM_BASE(SRAM_BASE),.SRAM_SIZE(SRAM_SIZE)) vector_unit (
        .clk,.rst_n(rst_n&&!pipe_fault),
        .cfg_addr(vec_we ? vec_addr : target_addr),.cfg_wdata(vec_we ? vec_wdata : target_wdata),
        .cfg_we(vec_we||vec_host_we),.cfg_re(target_re&&vec_select),.cfg_rdata(vec_rdata),.cfg_ready(vec_ready),
        .mem_valid(valid_raw[10]),.mem_write(cnn_write[10]),.mem_byte(cnn_byte[10]),
        .mem_addr(cnn_addr[351:320]),.mem_wdata(cnn_wdata[351:320]),
        .mem_ready(cnn_ready[10]),.mem_response(cnn_response[10]),.mem_rdata(cnn_rdata[351:320]),
        .mem_fault(cnn_mem_fault),.busy(vec_busy),.done(vec_done),.fault(vec_fault),
        .result_code(vec_code),.cycles(vec_cycles),.jobs(vec_jobs),
        .memory_state(vec_state),.reads(vec_reads),.writes(vec_writes),
        .stalls(vec_stalls),.pending_registers(vec_pending)
    );
endmodule
