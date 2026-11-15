// Real six-module SoC. Testbench only initializes memory and observes outputs;
// all configuration requests are executed by the production RV32I CPU.
module hybrid_soc_harness (
    input logic clk,rst_n,
    input logic [31:0] debug_addr,output wire [31:0] debug_data,
    output wire [31:0] status,phase,cpu_pc,mmio_addr,mmio_wdata,mmio_rdata,
    output wire mmio_re,mmio_we,mmio_ready,cmd_busy,cmd_done,cmd_error,
    output wire nv_irq,fault,vec_busy,vec_done,
    output wire [31:0] vec_jobs,vec_code,vec_cycles,vec_reads,vec_writes,vec_stalls,vec_pending,
    output wire [31:0] read_beats,write_beats,vec_addr,vec_wdata,vec_rdata,
    output wire [10:0] cnn_valid,cnn_ready,cnn_response,cnn_write,
    output wire [2:0] vec_state,
    output wire [1:0] config_state,
    output wire [2:0] read_state,write_state,
    output wire uart_tx,load_req
);
    face_soc_hybrid_top #(.IMEM_INIT_FILE("cpu.hex")) dut (
        .sys_clk(clk),.rst_n_in(rst_n),.uart_rx(1'b1),.uart_tx,
        .led_ready(),.led_busy(),.led_error()
    );
    logic [31:0] preload[0:65535];
    initial begin
        $readmemh("sram.hex",preload);
        for(integer i=0;i<65536;i++) dut.u_datasram.mem[i%4][i/4]=preload[i];
    end
    assign debug_data=dut.u_datasram.mem[(debug_addr>>2)%4][(debug_addr>>2)/4];
    assign status=dut.u_datasram.mem[(32'h80>>2)%4][(32'h80>>2)/4];
    assign phase=dut.u_datasram.mem[(32'h84>>2)%4][(32'h84>>2)/4];
    assign cpu_pc=dut.imem_addr;
    assign mmio_addr=dut.mmio_addr;assign mmio_wdata=dut.mmio_wdata;assign mmio_rdata=dut.mmio_rdata;
    assign mmio_re=dut.mmio_re;assign mmio_we=dut.mmio_we;assign mmio_ready=dut.mmio_ready;
    assign cmd_busy=dut.u_cnn.cmd_busy;assign cmd_done=dut.u_cnn.cmd_done;assign cmd_error=dut.u_cnn.cmd_error;
    assign nv_irq=dut.u_cnn.nv_irq;assign fault=dut.cnn_fault;
    assign vec_busy=dut.u_cnn.vec_busy;assign vec_done=dut.u_cnn.vec_done;
    assign vec_jobs=dut.u_cnn.vec_jobs;assign vec_code=dut.u_cnn.vec_code;assign vec_cycles=dut.u_cnn.vec_cycles;
    assign vec_reads=dut.u_cnn.vec_reads;assign vec_writes=dut.u_cnn.vec_writes;assign vec_stalls=dut.u_cnn.vec_stalls;
    assign vec_pending=dut.u_cnn.vec_pending;assign vec_state=dut.u_cnn.vec_state;
    assign read_beats=dut.read_beats;assign write_beats=dut.write_beats;
    assign config_state=dut.config_state;assign read_state=dut.read_state;assign write_state=dut.write_state;
    assign cnn_valid=dut.cnn_valid;assign cnn_ready=dut.cnn_ready;assign cnn_response=dut.cnn_response;assign cnn_write=dut.cnn_write;
    assign vec_addr=dut.cnn_addr[95:64];assign vec_wdata=dut.cnn_wdata[95:64];assign vec_rdata=dut.cnn_rdata[95:64];
    assign load_req=dut.load_req;
endmodule
