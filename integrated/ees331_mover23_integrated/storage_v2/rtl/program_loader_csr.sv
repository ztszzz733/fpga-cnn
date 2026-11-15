// Parameterized service-domain register interface for downloading IMEM/RAM.
// The external GP0-to-CSR bridge and hardware CPU quiescence proof are separate.
module program_loader_csr #(
 parameter logic [31:0] BASE=32'h40001000
)(
 input logic clk,rst_n,app_halted,
 input logic bus_valid,bus_write,
 output wire bus_ready,
 input logic [31:0] bus_addr,bus_wdata,
 input logic [3:0] bus_wstrb,
 output logic bus_rsp_valid,
 input logic bus_rsp_ready,
 output logic [31:0] bus_rdata,
 output logic [31:0] bus_status,
 output wire imem_valid,imem_write,
 input logic imem_ready,imem_rsp_valid,imem_error,
 output wire [31:0] imem_addr,imem_wdata,
 output wire [3:0] imem_wstrb,
 output wire imem_rsp_ready,
 input logic [31:0] imem_rdata,
 output wire ram_valid,ram_write,
 input logic ram_ready,ram_rsp_valid,ram_error,
 output wire [31:0] ram_addr,ram_wdata,
 output wire [3:0] ram_wstrb,
 output wire ram_rsp_ready,
 input logic [31:0] ram_rdata
);
 typedef enum logic [1:0] {IDLE,ISSUE,WAIT_MEM} state_t;
 state_t state;
 logic target_q,write_q,done_q,error_q;
 logic [31:0] addr_q,data_q,read_q;
 logic [3:0] strb_q;
 wire [31:0] offset=bus_addr-BASE;
 wire select_ok=bus_addr>=BASE && offset<=32'h1c && bus_addr[1:0]==0;
 wire status_read=select_ok && !bus_write && (offset==32'h10 || offset==32'h18);
 wire take=bus_valid && bus_ready;
 wire selected_ready=target_q?ram_ready:imem_ready;
 wire selected_rsp=target_q?ram_rsp_valid:imem_rsp_valid;
 wire selected_error=target_q?ram_error:imem_error;
 wire [31:0] selected_data=target_q?ram_rdata:imem_rdata;
 assign bus_ready=rst_n && !bus_rsp_valid;
 assign imem_valid=state==ISSUE && !target_q;
 assign ram_valid=state==ISSUE && target_q;
 assign imem_write=write_q;assign ram_write=write_q;
 assign imem_addr=addr_q;assign ram_addr=addr_q;
 assign imem_wdata=data_q;assign ram_wdata=data_q;
 assign imem_wstrb=strb_q;assign ram_wstrb=strb_q;
 assign imem_rsp_ready=state==WAIT_MEM && !target_q;
 assign ram_rsp_ready=state==WAIT_MEM && target_q;
 always_ff @(posedge clk) begin
  if(!rst_n) begin
   state<=IDLE;target_q<=0;write_q<=0;addr_q<=0;data_q<=0;strb_q<=4'hf;
   done_q<=0;error_q<=0;read_q<=0;
   bus_rsp_valid<=0;bus_rdata<=0;bus_status<=0;
  end else begin
   if(bus_rsp_valid && bus_rsp_ready) bus_rsp_valid<=0;
   if(state==ISSUE && selected_ready) state<=WAIT_MEM;
   if(state==WAIT_MEM && selected_rsp) begin
    state<=IDLE;done_q<=1;error_q<=selected_error;
    if(!write_q && !selected_error) read_q<=selected_data;
   end
   if(take) begin
    bus_rsp_valid<=1;bus_status<=0;bus_rdata<=0;
    if(!select_ok) bus_status<=1;
    else if(bus_write && bus_wstrb!=4'hf) bus_status<=1;
    else if(state!=IDLE && !status_read) bus_status<=2;
    else if(bus_write) case(offset)
     32'h00: if(bus_wdata<=1) target_q<=bus_wdata[0];else bus_status<=1;
     32'h04: addr_q<=bus_wdata;
     32'h08: data_q<=bus_wdata;
     32'h0c: if(bus_wdata[31:4]==0) strb_q<=bus_wdata[3:0];else bus_status<=1;
     32'h10,32'h18: bus_status<=1;
     32'h14: begin
      if(bus_wdata!=1 && bus_wdata!=2) bus_status<=1;
      else if(!app_halted) bus_status<=3;
      else begin
       write_q<=bus_wdata==1;done_q<=0;error_q<=0;state<=ISSUE;
      end
     end
     32'h1c: if(bus_wdata[0]) begin done_q<=0;error_q<=0;end
     default: bus_status<=1;
    endcase
    else case(offset)
     32'h00: bus_rdata<={31'b0,target_q};
     32'h04: bus_rdata<=addr_q;
     32'h08: bus_rdata<=data_q;
     32'h0c: bus_rdata<={28'b0,strb_q};
     32'h10: bus_rdata<={28'b0,app_halted,error_q,done_q,(state!=IDLE)};
     32'h14: bus_rdata<=0;
     32'h18: bus_rdata<=read_q;
     32'h1c: bus_rdata<=0;
     default: bus_status<=1;
    endcase
   end
  end
 end
endmodule
