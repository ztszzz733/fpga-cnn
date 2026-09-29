`timescale 1ns/1ps
// Queue-only array accelerator: MMIO OP15 submits; descriptors OP0 Conv / OP1 DW.
module mobilefacenet_accelerator_top #(
    parameter [31:0] BASE_ADDR=32'h40000000,
    parameter TASK_PREFETCH_DEPTH=4
)(
    input wire clk,rst_n,input wire [31:0] mmio_addr,mmio_wdata,
    input wire mmio_we,mmio_re,output wire [31:0] mmio_rdata,output wire mmio_ready,
    output wire [31:0] mem_addr,mem_wdata,output wire mem_read,mem_write,
    input wire [31:0] mem_rdata,input wire mem_ready
);
    wire start,reset,core_busy,done,error,mem_idle;
    wire exec_start,exec_busy,exec_done,exec_error,queue_active,queue_done,queue_error,fetch_phase;
    wire fetch_valid,fetch_ready,fetch_response,bus_ready,bus_response;
    wire [31:0] fetch_addr,bus_rdata,task_ia,task_oa,task_wa,task_ba,task_fs,task_ch,task_lp;
    wire [31:0] queue_base,queue_completed,queue_fetched,queue_buffered;
    wire [63:0] queue_end;
    wire [3:0] task_op,queue_state,op;
    wire sx_busy,sx_done,sx_error,sx_valid,sx_write,sx_byte,array_running;
    wire [31:0] sx_addr,sx_wdata,ia,oa,wa,ba,fs,ch,lp;
    // Only a descriptor FIFO handshake can start the compute controller.
    wire sx_start=exec_start;
    assign exec_busy=sx_busy;assign exec_done=sx_done;assign exec_error=sx_error;
    assign core_busy=exec_busy || queue_active;
    assign done=queue_done;
    assign error=queue_error;
    assign fetch_ready=bus_ready && fetch_phase;
    assign fetch_response=bus_response && fetch_phase;
    accelerator_regs #(.BASE_ADDR(BASE_ADDR)) regs(clk,rst_n,mmio_addr,mmio_wdata,mmio_we,mmio_re,
        mmio_rdata,mmio_ready,start,reset,op,core_busy || !mem_idle,done,error,ia,oa,wa,ba,fs,ch,lp);
    task_queue_controller #(.PREFETCH_DEPTH(TASK_PREFETCH_DEPTH)) task_queue(
        .clk(clk),.rst_n(rst_n),.soft_reset(reset),.start(start),.op_type(op),
        .input_addr(ia),.feature_size(fs),
        .exec_busy(exec_busy),.exec_done(exec_done),.exec_error(exec_error),.mem_idle(mem_idle),.exec_start(exec_start),
        .task_op(task_op),.task_input(task_ia),.task_output(task_oa),.task_weight(task_wa),.task_bias(task_ba),
        .task_size(task_fs),.task_channels(task_ch),.task_param(task_lp),.active(queue_active),.done(queue_done),.error(queue_error),
        .fetch_phase(fetch_phase),.fetch_valid(fetch_valid),.fetch_ready(fetch_ready),.fetch_addr(fetch_addr),
        .fetch_rsp_valid(fetch_response),.fetch_rsp_data(bus_rdata),.queue_base(queue_base),.queue_end(queue_end),
        .completed(queue_completed),.fetched(queue_fetched),.buffered(queue_buffered),.debug_state(queue_state));
    // Stable debug hierarchy. There is no alternative compute engine.
    generate if(1) begin:systolic_path
        systolic_conv_controller engine(
            clk,rst_n,reset,sx_start,task_ia,task_oa,task_wa,task_ba,task_fs,task_ch,task_lp,task_op,
            queue_active,queue_base,queue_end,sx_busy,sx_done,sx_error,
            sx_valid,bus_ready && !fetch_phase && sx_busy,sx_write,sx_byte,sx_addr,sx_wdata,
            bus_response && !fetch_phase && sx_busy,bus_rdata,array_running);
    end endgenerate
    accelerator_mem_if memory_interface(clk,rst_n,reset,fetch_phase ? fetch_valid : sx_valid,bus_ready,
        fetch_phase ? 1'b0 : sx_write,fetch_phase ? 1'b0 : sx_byte,
        fetch_phase ? fetch_addr : sx_addr,sx_wdata,bus_response,bus_rdata,mem_idle,
        mem_addr,mem_wdata,mem_read,mem_write,mem_rdata,mem_ready);
endmodule
