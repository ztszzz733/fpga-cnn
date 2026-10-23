`timescale 1ns/1ps
module tb_self_conv_unit;
  localparam integer SIZE = 262144;
  localparam integer INPUT_ADDR = 4096, WEIGHT_ADDR = 65536, OUTPUT_ADDR = 131072;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, clear = 0, start = 0, depthwise = 0;
  logic [31:0] input_base, weight_base, output_base, width, height;
  logic [31:0] in_channels, out_channels, kernel, stride;
  wire busy, done, error, valid, write, byte_access, mac_fire;
  wire [31:0] addr, wdata, input_reads, weight_reads, mac_count;
  wire [3:0] phase;
  wire ready;
  logic response = 0;
  logic [31:0] rdata = 0;
  self_conv_engine #(.MAX_CHANNELS(512), .MAX_KERNEL(3), .TILE(2)) dut(.*);

  logic [7:0] memory [0:SIZE-1];
  logic [7:0] expected [0:SIZE-1];
  bit output_written [0:SIZE-1];
  logic pending = 0, saved_write = 0, saved_byte = 0;
  logic [31:0] saved_addr = 0, saved_data = 0;
  integer delay_left = 0, cycle = 0, request_count = 0;
  integer input_length = 0, weight_length = 0, output_length = 0;
  integer accepted_inputs = 0, accepted_weights = 0, completed_writes = 0;
  integer observed_macs = 0, checked_bytes = 0, illegal_count = 0;
  integer case_count = 0, metrics, outputs, start_cycle, current_case = -1;
  bit measuring = 0, holding = 0, forbidden_requests = 0;
  logic [65:0] held_request;
  assign ready = !pending && !response && !clear && cycle % 7 >= 2;

  // Delayed, one-outstanding SRAM model. Writes commit only at response time.
  // clear explicitly cancels the external outstanding transaction too.
  always @(posedge clk) begin
    cycle <= cycle + 1;
    response <= 0;
    if (cycle > 2000000) $fatal(1, "unit watchdog case=%0d phase=%0d", current_case, phase);
    if (!rst_n || clear) begin
      pending <= 0;
      response <= 0;
      holding <= 0;
    end else begin
      if (holding && (!valid || {write, byte_access, addr, wdata} !== held_request))
        $fatal(1, "request changed under backpressure case=%0d", current_case);
      holding <= valid && !ready;
      held_request <= {write, byte_access, addr, wdata};
      if (measuring && mac_fire) observed_macs++;
      if (done && (pending || response)) $fatal(1, "done before final write response drained");
      if (forbidden_requests && valid) $fatal(1, "invalid config asserted memory request");
      if (valid && ready) begin
        if (forbidden_requests) $fatal(1, "invalid config issued memory transaction");
        if (addr >= SIZE || (!byte_access && (addr[1:0] != 0 || addr + 3 >= SIZE)))
          $fatal(1, "invalid memory address %h", addr);
        if (write) begin
          if (byte_access || addr < OUTPUT_ADDR || addr + 4 > OUTPUT_ADDR + output_length)
            $fatal(1, "write outside output or not INT32 addr=%h", addr);
        end else if (addr >= INPUT_ADDR && addr < INPUT_ADDR + input_length) begin
          if (!byte_access) $fatal(1, "unit expects byte input reads");
          if (measuring) accepted_inputs++;
        end else if (addr >= WEIGHT_ADDR && addr < WEIGHT_ADDR + weight_length) begin
          if (!byte_access) $fatal(1, "unit expects byte weight reads");
          if (measuring) accepted_weights++;
        end else $fatal(1, "read outside input/weights addr=%h", addr);
        pending <= 1;
        delay_left <= request_count % 5;
        request_count++;
        saved_addr <= addr;
        saved_data <= wdata;
        saved_write <= write;
        saved_byte <= byte_access;
      end
      if (pending) begin
        if (delay_left != 0) delay_left <= delay_left - 1;
        else begin
          pending <= 0;
          response <= 1;
          if (saved_write) begin
            if (measuring) begin
              if (output_written[saved_addr]) $fatal(1, "duplicate output write addr=%h", saved_addr);
              output_written[saved_addr] = 1;
              completed_writes++;
            end
            for (integer b = 0; b < 4; b++) memory[saved_addr+b] <= saved_data[b*8+:8];
            rdata <= 0;
          end else begin
            rdata <= saved_byte ? {24'b0, memory[saved_addr]} :
                     {memory[saved_addr+3], memory[saved_addr+2], memory[saved_addr+1], memory[saved_addr]};
          end
        end
      end
    end
  end

  task automatic configure(input integer w, h, ci, co, k, s, dw);
    input_base = INPUT_ADDR; weight_base = WEIGHT_ADDR; output_base = OUTPUT_ADDR;
    width = w; height = h; in_channels = ci; out_channels = co;
    kernel = k; stride = s; depthwise = dw;
  endtask
  task automatic launch;
    @(negedge clk); start = 1;
    @(negedge clk); start = 0;
  endtask
  task automatic cancel_job;
    @(negedge clk); clear = 1;
    repeat (3) @(negedge clk);
    if (busy || valid || done || error || pending || response)
      $fatal(1, "clear did not cancel engine and external SRAM");
    clear = 0;
    repeat (2) @(negedge clk);
  endtask
  task automatic run_case(input integer id, input string name,
                         input integer w, h, ci, co, k, s, dw,
                         input integer ni, nw, no, restart, latch_config);
    string prefix;
    integer elapsed;
    current_case = id;
    input_length = ni; weight_length = nw; output_length = no;
    for (integer a = 0; a < SIZE; a++) begin memory[a] = 8'ha5; output_written[a] = 0; end
    prefix = $sformatf("case_%02d", id);
    $readmemh({prefix, "_input.hex"}, memory, INPUT_ADDR, INPUT_ADDR+ni-1);
    $readmemh({prefix, "_weight.hex"}, memory, WEIGHT_ADDR, WEIGHT_ADDR+nw-1);
    $readmemh({prefix, "_expected.hex"}, expected, 0, no-1);
    configure(w,h,ci,co,k,s,dw);
    if (restart != 0) begin
      launch();
      if (restart == 1) wait(pending && !saved_write);
      else wait(pending && saved_write);
      cancel_job();
      for (integer b = 0; b < no; b++) memory[OUTPUT_ADDR+b] = 8'ha5;
    end
    accepted_inputs = 0; accepted_weights = 0; completed_writes = 0; observed_macs = 0;
    start_cycle = cycle; measuring = 1;
    launch();
    if (latch_config) begin
      input_base = 0; weight_base = 0; output_base = 0;
      width = 0; height = 0; in_channels = 0; out_channels = 0;
      kernel = 0; stride = 0; depthwise = !dw;
    end
    wait(done || error);
    @(negedge clk);
    if (error) $fatal(1, "unexpected engine error case=%0d", id);
    elapsed = cycle-start_cycle;
    measuring = 0;
    if (completed_writes*4 != no) $fatal(1, "output count mismatch case=%0d got=%0d want=%0d", id, completed_writes*4, no);
    if (input_reads != accepted_inputs || weight_reads != accepted_weights || mac_count != observed_macs)
      $fatal(1, "counter mismatch case=%0d inputs=%0d/%0d weights=%0d/%0d mac=%0d/%0d", id,
             input_reads,accepted_inputs,weight_reads,accepted_weights,mac_count,observed_macs);
    for (integer b = 0; b < no; b++) begin
      if (memory[OUTPUT_ADDR+b] !== expected[b])
        $fatal(1, "numeric mismatch case=%0d byte=%0d got=%h expected=%h", id,b,memory[OUTPUT_ADDR+b],expected[b]);
      $fwrite(outputs, "%c", memory[OUTPUT_ADDR+b]);
    end
    for (integer b = 1; b <= 64; b++)
      if (memory[OUTPUT_ADDR-b] !== 8'ha5 || memory[OUTPUT_ADDR+no+b-1] !== 8'ha5)
        $fatal(1, "output guard corruption case=%0d", id);
    checked_bytes += no;
    if (case_count) $fwrite(metrics, ",\n");
    $fwrite(metrics, "{\"id\":%0d,\"name\":\"%s\",\"cycles\":%0d,\"input_reads\":%0d,\"weight_reads\":%0d,\"mac_count\":%0d,\"writes\":%0d}",
            id,name,elapsed,input_reads,weight_reads,mac_count,completed_writes);
    case_count++;
    $display("PASS case=%0d name=%s cycles=%0d input_reads=%0d weight_reads=%0d macs=%0d", id,name,elapsed,input_reads,weight_reads,mac_count);
    repeat (3) @(negedge clk);
  endtask

  task automatic invalid_case(input integer id);
    current_case = 100+id;
    configure(5,5,3,3,3,1,0);
    case (id)
      0: width = 0;
      1: height = 2;
      2: in_channels = 0;
      3: out_channels = 0;
      4: kernel = 2;
      5: stride = 0;
      6: stride = 3;
      7: in_channels = 513;
      8: begin depthwise = 1; out_channels = 2; end
      9: output_base = OUTPUT_ADDR+1;
      10: out_channels = 513;
      11: width = 65536;
      12: input_base = 32'hfffffffe;
      13: weight_base = 32'hfffffffc;
      14: output_base = 32'hfffffff0;
      15: output_base = INPUT_ADDR+4;
      16: output_base = WEIGHT_ADDR;
      17: kernel = 7;
    endcase
    forbidden_requests = 1;
    launch();
    wait(error || done);
    if (!error || valid || pending || done) $fatal(1, "invalid config not rejected id=%0d", id);
    repeat (5) @(negedge clk);
    if (busy || valid || pending) $fatal(1, "invalid config did not return idle id=%0d", id);
    illegal_count++;
    cancel_job();
    forbidden_requests = 0;
  endtask

  initial begin
    configure(5,5,3,3,3,1,0);
    metrics = $fopen("metrics.json", "w"); outputs = $fopen("outputs.bin", "wb");
    if (!metrics || !outputs) $fatal(1, "cannot open result files");
    $fwrite(metrics, "{\"cases\":[\n");
    repeat (5) @(negedge clk); rst_n = 1;
    `include "self_conv_cases.svh"
    for (integer i = 0; i < 18; i++) invalid_case(i);
    $fwrite(metrics, "\n],\"checked_bytes\":%0d,\"illegal_configurations\":%0d,\"clear_restarts\":2,\"configuration_latching\":true}\n", checked_bytes,illegal_count);
    $fclose(metrics); $fclose(outputs);
    $display("PASS tb_self_conv_unit cases=%0d checked_bytes=%0d illegal=%0d", case_count,checked_bytes,illegal_count);
    $finish;
  end
endmodule
