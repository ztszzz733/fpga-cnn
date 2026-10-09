`timescale 1ns/1ps
// Bounded out-of-order issue window. Oldest eligible task wins.
// Check active AND older queued tasks for RAW/WAR/WAW before bypass.
// Units 0/1: shared array contexts; 2:ReLU6 3:ADD 4:ReLU 5:PReLU 6:Pool 7:Requant.
module streaming_task_scheduler #(parameter PREFETCH_DEPTH=4)(
    input wire clk,rst_n,soft_reset,start,input wire [3:0] op_type,
    input wire [31:0] input_addr,feature_size,
    input wire [7:0] exec_busy,exec_done,exec_error,input wire mem_idle,
    output wire [7:0] context_start,output wire exec_start,output wire [255:0] task_descriptor,
    output wire active,done,error,output wire fetch_valid,input wire fetch_ready,
    output wire [31:0] fetch_addr,input wire fetch_rsp_valid,input wire [31:0] fetch_rsp_data,
    output reg [31:0] queue_base,output wire [63:0] queue_end,
    output reg [31:0] completed,fetched,dispatched,output reg [31:0] buffered,
    output wire [3:0] debug_state,output reg [7:0] allocated,
    output reg [2:0] base0,base1,output reg [3:0] rows0,rows1,
    output wire [3:0] dispatch_rows,output wire [31:0] task_id0,task_id1,
    output reg hazard_wait,resource_wait,output wire [31:0] dispatch_id,
    output wire [255:0] unit_task_ids
);
    localparam IDLE=0,VALIDATE=1,RUN=2,DRAIN=5,DONE=6,ERROR=7;
    reg [3:0] state;reg [31:0] total;reg failed;
    reg [511:0] active_spans[0:7];reg [31:0] ids[0:7];
    reg [255:0] window_data[0:PREFETCH_DEPTH-1];
    reg [511:0] window_spans[0:PREFETCH_DEPTH-1];
    reg [31:0] sequence_id[0:PREFETCH_DEPTH-1];
    reg [PREFETCH_DEPTH-1:0] occupied,legal;
    wire [255:0] reader_data;wire reader_idle,reader_valid,reader_ready;
    wire accept_start=state==IDLE && start && mem_idle && exec_busy==0 && !soft_reset;
    wire begin_queue=accept_start && op_type==15;
    wire flush=soft_reset || begin_queue;
    assign active=state!=IDLE;assign done=state==DONE;assign error=state==ERROR;
    assign debug_state=state;assign queue_end={32'd0,queue_base}+({32'd0,total}<<5);
    wire legal_queue=queue_base[4:0]==0 && total!=0 && queue_end<=64'h100000000;
    wire incoming_legal;wire [511:0] incoming_spans;
    task_descriptor_info info(reader_data,queue_base,queue_end,incoming_legal,incoming_spans);
    function intersects(input [63:0] a0,a1,b0,b1);
        intersects=a0<a1 && b0<b1 && a0<b1 && b0<a1;
    endfunction
    function conflicts(input [511:0] a,b);
        integer j;begin
            conflicts=0;
            for(j=0;j<4;j=j+1) begin
                if(intersects(a[384+:64],a[448+:64],b[j*128+:64],b[j*128+64+:64])) conflicts=1;
                if(intersects(b[384+:64],b[448+:64],a[j*128+:64],a[j*128+64+:64])) conflicts=1;
            end
        end
    endfunction
    reg [7:0] used_rows;reg [3:0] best_length;reg [2:0] best_base;
    integer r,run_length,run_base;
    always @* begin
        used_rows=0;best_length=0;best_base=0;run_length=0;run_base=0;
        for(r=0;r<8;r=r+1) begin
            used_rows[r]=(allocated[0] && r>=base0 && r<({1'b0,base0}+rows0)) ||
                         (allocated[1] && r>=base1 && r<({1'b0,base1}+rows1));
            if(!used_rows[r]) begin
                if(run_length==0) run_base=r;
                run_length=run_length+1;
                if(run_length>best_length) begin best_length=run_length;best_base=run_base;end
            end else run_length=0;
        end
    end
    integer i,j,free_slot,oldest,selected,unit_candidate,chosen;
    reg blocked,available;
    always @* begin
        free_slot=-1;oldest=-1;selected=-1;chosen=0;buffered=0;
        hazard_wait=0;resource_wait=0;blocked=0;available=0;unit_candidate=0;
        for(i=0;i<PREFETCH_DEPTH;i=i+1) begin
            if(!occupied[i] && free_slot<0) free_slot=i;
            if(occupied[i]) begin
                buffered=buffered+1;
                if(oldest<0) oldest=i;
                else if(sequence_id[i]<sequence_id[oldest]) oldest=i;
                blocked=0;
                for(j=0;j<8;j=j+1)
                    if(allocated[j] && conflicts(window_spans[i],active_spans[j])) blocked=1;
                for(j=0;j<PREFETCH_DEPTH;j=j+1)
                    if(occupied[j] && sequence_id[j]<sequence_id[i] &&
                       (!legal[j] || conflicts(window_spans[i],window_spans[j]))) blocked=1;
                case(window_data[i][7:0])
                    0,1,9:unit_candidate=(!allocated[0] && !exec_busy[0]) ? 0 : 1;
                    2:unit_candidate=2;3:unit_candidate=3;6:unit_candidate=4;
                    7:unit_candidate=5;8:unit_candidate=6;10:unit_candidate=7;
                    default:unit_candidate=0;
                endcase
                available=!allocated[unit_candidate] && !exec_busy[unit_candidate] &&
                    (unit_candidate>=2 || best_length!=0);
                if(legal[i] && blocked) hazard_wait=state==RUN;
                if(legal[i] && !available) resource_wait=state==RUN;
                if(legal[i] && !blocked && available) begin
                    if(selected<0) begin selected=i;chosen=unit_candidate;end
                    else if(sequence_id[i]<sequence_id[selected]) begin selected=i;chosen=unit_candidate;end
                end
            end
        end
    end
    // Stable selected descriptor through the launch edge; aliases retained for debug.
    wire head_valid=selected>=0;
    wire head_ready=state==RUN && exec_error==0 && !soft_reset && !(oldest>=0 && !legal[oldest]);
    wire [255:0] head_data=selected>=0 ? window_data[selected] : 256'd0;
    assign exec_start=head_valid && head_ready;
    assign context_start=exec_start ? (8'b1<<chosen) : 8'd0;
    assign task_descriptor=head_data;
    assign dispatch_id=selected>=0 ? sequence_id[selected] : 0;
    wire [15:0] need_rows=head_data[223:208];
    assign dispatch_rows=need_rows<best_length ? need_rows[3:0] : best_length;
    assign task_id0=ids[0];assign task_id1=ids[1];
    genvar g;generate for(g=0;g<8;g=g+1) begin:debug_ids
        assign unit_task_ids[g*32+:32]=ids[g];
    end endgenerate
    assign reader_ready=state==RUN && free_slot>=0 && !soft_reset;
    task_descriptor_reader reader(clk,rst_n,flush || state==DRAIN,
        state==RUN && reader_idle && reader_ready && fetched<total,queue_base+(fetched<<5),reader_idle,
        fetch_valid,fetch_ready,fetch_addr,fetch_rsp_valid,fetch_rsp_data,reader_valid,reader_ready,reader_data);
    integer s,finished;
    always @* begin
        finished=0;
        for(integer c=0;c<8;c=c+1) if(allocated[c] && exec_done[c]) finished=finished+1;
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;total<=0;failed<=0;queue_base<=0;completed<=0;fetched<=0;dispatched<=0;
            allocated<=0;base0<=0;base1<=0;rows0<=0;rows1<=0;occupied<=0;legal<=0;
            for(s=0;s<8;s=s+1) begin ids[s]<=0;active_spans[s]<=0;end
            for(s=0;s<PREFETCH_DEPTH;s=s+1) begin window_data[s]<=0;window_spans[s]<=0;sequence_id[s]<=0;end
        end else if(soft_reset) begin
            state<=IDLE;allocated<=0;occupied<=0;legal<=0;completed<=0;fetched<=0;dispatched<=0;failed<=0;
        end else begin
            for(s=0;s<8;s=s+1) if(allocated[s] && (exec_done[s] || exec_error[s])) allocated[s]<=0;
            if(finished!=0) completed<=completed+finished;
            case(state)
                IDLE:if(accept_start) begin
                    completed<=0;fetched<=0;dispatched<=0;failed<=0;allocated<=0;occupied<=0;legal<=0;
                    if(begin_queue) begin queue_base<=input_addr;total<=feature_size;state<=VALIDATE;end
                    else state<=ERROR;
                end
                VALIDATE:state<=legal_queue ? RUN : ERROR;
                RUN:begin
                    if(reader_valid && reader_ready) begin
                        fetched<=fetched+1;occupied[free_slot]<=1;legal[free_slot]<=incoming_legal;
                        window_data[free_slot]<=reader_data;window_spans[free_slot]<=incoming_spans;sequence_id[free_slot]<=fetched;
                    end
                    if(exec_start) begin
                        dispatched<=dispatched+1;occupied[selected]<=0;
                        allocated[chosen]<=1;active_spans[chosen]<=window_spans[selected];ids[chosen]<=dispatch_id;
                        if(chosen==0) begin base0<=best_base;rows0<=dispatch_rows;end
                        if(chosen==1) begin base1<=best_base;rows1<=dispatch_rows;end
                    end
                    if(exec_error!=0 || (oldest>=0 && !legal[oldest])) begin failed<=1;state<=DRAIN;end
                    else if(completed==total && allocated==0) state<=DRAIN;
                end
                DRAIN:if(allocated==0 && exec_busy==0 && mem_idle) begin occupied<=0;state<=failed ? ERROR : DONE;end
                DONE:state<=IDLE;ERROR:state<=IDLE;default:state<=IDLE;
            endcase
        end
    end
endmodule
