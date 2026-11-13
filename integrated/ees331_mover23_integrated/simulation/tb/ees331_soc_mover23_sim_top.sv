// Test-only observation wrapper for the 23-client DATA MOVER top.
module ees331_soc_mover23_sim_top (
input wire FCLK_CLK0, FCLK_RESET0_N,
 output wire M_AXI_GP0_ACLK, S_AXI_HP0_ACLK,
 input wire [31:0] M_AXI_GP0_AWADDR,
 input wire [31:0] M_AXI_GP0_ARADDR,
 input wire [31:0] M_AXI_GP0_WDATA,
 output wire [31:0] M_AXI_GP0_RDATA,
 input wire [11:0] M_AXI_GP0_AWID,
 input wire [11:0] M_AXI_GP0_ARID,
 input wire [11:0] M_AXI_GP0_WID,
 input wire [3:0] M_AXI_GP0_AWLEN,
 input wire [3:0] M_AXI_GP0_ARLEN,
 input wire [2:0] M_AXI_GP0_AWSIZE,
 input wire [2:0] M_AXI_GP0_ARSIZE,
 input wire [1:0] M_AXI_GP0_AWBURST,
 input wire [1:0] M_AXI_GP0_ARBURST,
 input wire [1:0] M_AXI_GP0_AWLOCK,
 input wire [1:0] M_AXI_GP0_ARLOCK,
 input wire [3:0] M_AXI_GP0_AWCACHE,
 input wire [3:0] M_AXI_GP0_ARCACHE,
 input wire [2:0] M_AXI_GP0_AWPROT,
 input wire [2:0] M_AXI_GP0_ARPROT,
 input wire [3:0] M_AXI_GP0_AWQOS,
 input wire [3:0] M_AXI_GP0_ARQOS,
 input wire [3:0] M_AXI_GP0_WSTRB,
 input wire M_AXI_GP0_AWVALID,
 input wire M_AXI_GP0_WVALID,
 input wire M_AXI_GP0_WLAST,
 input wire M_AXI_GP0_BREADY,
 input wire M_AXI_GP0_ARVALID,
 input wire M_AXI_GP0_RREADY,
 output wire [11:0] M_AXI_GP0_BID,
 output wire [11:0] M_AXI_GP0_RID,
 output wire [1:0] M_AXI_GP0_BRESP,
 output wire [1:0] M_AXI_GP0_RRESP,
 output wire M_AXI_GP0_AWREADY,
 output wire M_AXI_GP0_WREADY,
 output wire M_AXI_GP0_BVALID,
 output wire M_AXI_GP0_ARREADY,
 output wire M_AXI_GP0_RVALID,
 output wire M_AXI_GP0_RLAST,
 output wire [31:0] S_AXI_HP0_AWADDR,
 output wire [31:0] S_AXI_HP0_ARADDR,
 output wire [63:0] S_AXI_HP0_WDATA,
 input wire [63:0] S_AXI_HP0_RDATA,
 output wire [5:0] S_AXI_HP0_AWID,
 output wire [5:0] S_AXI_HP0_ARID,
 output wire [5:0] S_AXI_HP0_WID,
 output wire [3:0] S_AXI_HP0_AWLEN,
 output wire [3:0] S_AXI_HP0_ARLEN,
 output wire [2:0] S_AXI_HP0_AWSIZE,
 output wire [2:0] S_AXI_HP0_ARSIZE,
 output wire [1:0] S_AXI_HP0_AWBURST,
 output wire [1:0] S_AXI_HP0_ARBURST,
 output wire [1:0] S_AXI_HP0_AWLOCK,
 output wire [1:0] S_AXI_HP0_ARLOCK,
 output wire [3:0] S_AXI_HP0_AWCACHE,
 output wire [3:0] S_AXI_HP0_ARCACHE,
 output wire [2:0] S_AXI_HP0_AWPROT,
 output wire [2:0] S_AXI_HP0_ARPROT,
 output wire [3:0] S_AXI_HP0_AWQOS,
 output wire [3:0] S_AXI_HP0_ARQOS,
 output wire [7:0] S_AXI_HP0_WSTRB,
 output wire S_AXI_HP0_AWVALID,
 output wire S_AXI_HP0_WVALID,
 output wire S_AXI_HP0_WLAST,
 output wire S_AXI_HP0_BREADY,
 output wire S_AXI_HP0_ARVALID,
 output wire S_AXI_HP0_RREADY,
 input wire [5:0] S_AXI_HP0_BID,
 input wire [5:0] S_AXI_HP0_RID,
 input wire [1:0] S_AXI_HP0_BRESP,
 input wire [1:0] S_AXI_HP0_RRESP,
 input wire S_AXI_HP0_AWREADY,
 input wire S_AXI_HP0_WREADY,
 input wire S_AXI_HP0_BVALID,
 input wire S_AXI_HP0_ARREADY,
 input wire S_AXI_HP0_RVALID,
 input wire S_AXI_HP0_RLAST,
 output wire [22:0] debug_unit_start,debug_unit_active,debug_completion,debug_work,
 output wire [252:0] debug_node,
 output wire [22:0] debug_valid,debug_write,debug_byte,debug_ready,debug_response,
 output wire [735:0] debug_addr,debug_wdata,debug_rdata,
 output wire [11:0] debug_completed,
 output wire debug_error,debug_fault,
 output wire debug_cpu_re,debug_cpu_we,
 output wire [31:0] debug_cpu_addr,
 output wire [31:0] debug_page_misses,debug_mover_read_bytes,debug_mover_write_bytes,
 output wire [2:0] debug_memory_state,
 output wire [3:0] debug_mover_state,
 output wire [22:0][3:0] debug_operator_state,
 output wire [22:0] debug_operator_busy,
 output wire debug_cnn_running,debug_cnn_finished,debug_mmio_we,
 output wire [31:0] debug_mmio_addr,debug_mmio_data
);
 face_soc_ees331_mover_top #(.POOL23(1),.CNN_FRAMES(5),
  .IMEM_INIT_FILE("firmware/ees331_cpu/program_ram_probe.mem")) dut(.*);
 assign debug_unit_start=dut.u_cnn.unit_start;
 assign debug_unit_active=dut.u_cnn.unit_active;
 assign debug_completion=dut.u_cnn.completion_pulse;
 assign debug_work=dut.u_cnn.operator_work;
 assign debug_node=dut.u_cnn.unit_node;
 assign debug_completed=dut.u_cnn.completed_count;
 assign debug_error=dut.u_cnn.error;
 assign debug_fault=dut.cnn_mem_fault;
 assign debug_cpu_re=dut.dmem_re;
 assign debug_cpu_we=dut.dmem_we;
 assign debug_cpu_addr=dut.dmem_addr;
 assign debug_page_misses=dut.u_datasram.cache.misses;
 assign debug_mover_read_bytes=dut.u_datasram.cache.ddr_read_bytes;
 assign debug_mover_write_bytes=dut.u_datasram.cache.ddr_write_bytes;
 assign debug_valid=dut.cnn_valid;assign debug_write=dut.cnn_write;
 assign debug_byte=dut.cnn_byte;assign debug_ready=dut.cnn_ready;
 assign debug_response=dut.cnn_response;assign debug_addr=dut.cnn_addr;
 assign debug_wdata=dut.cnn_wdata;assign debug_rdata=dut.cnn_rdata;

 assign debug_memory_state=dut.u_datasram.cache.state;
 assign debug_mover_state=dut.u_datasram.cache.mover.state;
 assign debug_operator_busy=dut.u_cnn.operator_busy;
 assign debug_cnn_running=dut.u_cnn.core.running;
 assign debug_cnn_finished=dut.u_cnn.core.finished;
 assign debug_mmio_we=dut.cnn_mmio_we;
 assign debug_mmio_addr=dut.cnn_mmio_addr;
 assign debug_mmio_data=dut.cnn_mmio_wdata;
 assign debug_operator_state[0]=dut.u_cnn.core.engines[0].latest_k3.convolution.state;
 assign debug_operator_state[1]=dut.u_cnn.core.engines[1].latest_k3.convolution.state;
 assign debug_operator_state[2]=dut.u_cnn.core.engines[2].latest_k3.convolution.state;
 assign debug_operator_state[3]=dut.u_cnn.core.engines[3].latest_k3.convolution.state;
 assign debug_operator_state[4]=dut.u_cnn.core.engines[4].latest_k1.convolution.state;
 assign debug_operator_state[5]=dut.u_cnn.core.engines[5].latest_k1.convolution.state;
 assign debug_operator_state[6]=dut.u_cnn.core.engines[6].latest_k1.convolution.state;
 assign debug_operator_state[7]=dut.u_cnn.core.engines[7].latest_k1.convolution.state;
 assign debug_operator_state[8]=dut.u_cnn.core.engines[8].latest_k1.convolution.state;
 assign debug_operator_state[9]=dut.u_cnn.core.engines[9].latest_k1.convolution.state;
 assign debug_operator_state[10]=dut.u_cnn.core.engines[10].latest_k1.convolution.state;
 assign debug_operator_state[11]=dut.u_cnn.core.engines[11].latest_k1.convolution.state;
 assign debug_operator_state[12]=dut.u_cnn.core.engines[12].latest_k1.convolution.state;
 assign debug_operator_state[13]=dut.u_cnn.core.engines[13].latest_k1.convolution.state;
 assign debug_operator_state[14]=dut.u_cnn.core.engines[14].latest_k1.convolution.state;
 assign debug_operator_state[15]=dut.u_cnn.core.engines[15].latest_k1.convolution.state;
 assign debug_operator_state[16]=dut.u_cnn.core.dw7.state;
 assign debug_operator_state[17]=dut.u_cnn.core.postprocessing[17].latest_post.post.state;
 assign debug_operator_state[18]=dut.u_cnn.core.postprocessing[18].latest_post.post.state;
 assign debug_operator_state[19]=dut.u_cnn.core.postprocessing[19].latest_post.post.state;
 assign debug_operator_state[20]=dut.u_cnn.core.postprocessing[20].latest_post.post.state;
 assign debug_operator_state[21]=dut.u_cnn.core.postprocessing[21].latest_post.post.state;
 assign debug_operator_state[22]=dut.u_cnn.core.padding.state;
endmodule
