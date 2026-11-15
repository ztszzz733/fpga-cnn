// Two SRAM slots, strictly ordered producer/consumer. No arithmetic in this block.
// Descriptor: {config_ptr, destination, byte_count, program_mode}, 16 bytes.
// Config image: 24 native NEureka words; output pointer is replaced by slot A/B.
module neureka_tile_scheduler #(
    parameter logic [31:0] BASE=32'h40000000, SRAM_BASE=0, SRAM_SIZE=32'h40000,
    parameter integer MAX_CYCLES=50_000_000
)(
    input logic clk,rst_n,
    input logic [31:0] cfg_addr,cfg_wdata,input logic cfg_we,host_reject,
    output logic [31:0] cfg_rdata,
    output logic busy,done,fault,output logic [31:0] error_code,
    output logic mem_valid,output logic [31:0] mem_addr,
    input logic mem_ready,mem_response,input logic [31:0] mem_rdata,input logic mem_fault,
    output wire conv_start,output wire [31:0] conv_config_address,
    input logic conv_busy,conv_done,conv_error,
    input logic conv_cfg_valid,input logic [31:0] conv_cfg_addr,
    output wire conv_cfg_ready,output logic conv_cfg_response,output logic [31:0] conv_cfg_rdata,
    output logic vec_we,output logic [31:0] vec_addr,vec_wdata,
    input logic vec_busy,vec_done,vec_fault,vec_loaded,vec_idle,
    output logic [31:0] cycles,overlap_cycles,produced,completed,
    output wire [3:0] slot_status,
    output wire [31:0] conv_output_base,conv_output_capacity
);
    localparam [1:0] FREE=0,FILL=1,READY=2,DRAIN=3;
    typedef enum logic [2:0] {P_IDLE,P_DESC,P_DESC_WAIT,P_CONFIG,P_CONFIG_WAIT,P_CHECK,P_START,P_RUN} pstate_t;
    typedef enum logic [3:0] {V_IDLE,V_SRC,V_DST,V_COUNT,V_MODE,V_START,V_ACCEPT,V_RUN,V_DRAIN} vstate_t;
    pstate_t ps;
    vstate_t vs;
    logic [1:0] slots[0:1];
    logic [31:0] table_ptr,tile_count,buffers[0:1],capacity,flags;
    logic [31:0] dst[0:1],length[0:1],mode[0:1],config_ptr,image[0:23];
    logic [4:0] word_index;
    logic rejected;
    wire pslot=produced[0],vslot=completed[0];
    wire [32:0] table_bytes={1'b0,tile_count}<<4;
    function automatic logic in_sram(input logic [31:0] a,input logic [32:0] n);
        in_sram=n!=0 && a>=SRAM_BASE && {1'b0,a}+n<={1'b0,SRAM_BASE}+{1'b0,SRAM_SIZE};
    endfunction
    function automatic logic intersects(input logic [31:0] a,input logic [32:0] an,
                                         input logic [31:0] b,input logic [32:0] bn);
        intersects=({1'b0,a}<{1'b0,b}+bn) && ({1'b0,b}<{1'b0,a}+an);
    endfunction
    wire valid_batch=tile_count!=0 && tile_count<=32'h0fffffff && table_ptr[1:0]==0 &&
        capacity[1:0]==0 && buffers[0][1:0]==0 && buffers[1][1:0]==0 &&
        in_sram(table_ptr,table_bytes) && in_sram(buffers[0],{1'b0,capacity}) &&
        in_sram(buffers[1],{1'b0,capacity}) &&
        !intersects(buffers[0],{1'b0,capacity},buffers[1],{1'b0,capacity}) &&
        !intersects(buffers[0],{1'b0,capacity},table_ptr,table_bytes) &&
        !intersects(buffers[1],{1'b0,capacity},table_ptr,table_bytes);
    wire valid_tile=length[pslot]!=0 && length[pslot]<=capacity &&
        in_sram(dst[pslot],{1'b0,length[pslot]}) &&
        !intersects(dst[pslot],{1'b0,length[pslot]},buffers[0],{1'b0,capacity}) &&
        !intersects(dst[pslot],{1'b0,length[pslot]},buffers[1],{1'b0,capacity}) &&
        !intersects(dst[pslot],{1'b0,length[pslot]},table_ptr,table_bytes);
    assign slot_status={slots[1],slots[0]};
    assign conv_output_base=buffers[pslot];
    assign conv_output_capacity=capacity;
    assign conv_start=busy && !fault && ps==P_START;
    assign conv_config_address=0;
    assign conv_cfg_ready=!fault;
    always_ff @(posedge clk) begin
        if(!rst_n) begin conv_cfg_response<=0;conv_cfg_rdata<=0;end
        else begin
            conv_cfg_response<=conv_cfg_valid && conv_cfg_ready;
            if(conv_cfg_valid && conv_cfg_ready) begin
                if(conv_cfg_addr==8) conv_cfg_rdata<=buffers[pslot];
                else if(conv_cfg_addr<96) conv_cfg_rdata<=image[conv_cfg_addr[6:2]];
                else conv_cfg_rdata<=0;
            end
        end
    end
    always_comb begin
        case(cfg_addr-BASE)
            0:cfg_rdata=0;
            4:cfg_rdata={28'b0,rejected,fault,done,busy};
            8:cfg_rdata=table_ptr;12:cfg_rdata=tile_count;
            16:cfg_rdata=buffers[0];20:cfg_rdata=buffers[1];
            24:cfg_rdata=capacity;28:cfg_rdata=flags;
            32:cfg_rdata=completed;36:cfg_rdata=cycles;40:cfg_rdata=overlap_cycles;
            44:cfg_rdata=error_code;48:cfg_rdata=produced;
            52:cfg_rdata={28'b0,slot_status};
            default:cfg_rdata=32'hdeadbad0;
        endcase
        mem_valid=busy && !fault && (ps==P_DESC || ps==P_CONFIG);
        mem_addr=ps==P_DESC ? table_ptr+(produced<<4)+{25'b0,word_index,2'b0} :
                                            config_ptr+{25'b0,word_index,2'b0};
        vec_we=busy && !fault && vs>=V_SRC && vs<=V_START;
        vec_addr=BASE+32'h40000;
        vec_wdata=1;
        case(vs)
            V_SRC:begin vec_addr=BASE+32'h40004;vec_wdata=buffers[vslot];end
            V_DST:begin vec_addr=BASE+32'h40008;vec_wdata=dst[vslot];end
            V_COUNT:begin vec_addr=BASE+32'h4000c;vec_wdata=length[vslot];end
            V_MODE:begin vec_addr=BASE+32'h40010;vec_wdata=mode[vslot];end
            default:;
        endcase
    end
    always_ff @(posedge clk) begin
        if(!rst_n) begin
            busy<=0;done<=0;fault<=0;error_code<=0;rejected<=0;
            table_ptr<=0;tile_count<=0;capacity<=0;flags<=0;
            buffers[0]<=0;buffers[1]<=0;slots[0]<=FREE;slots[1]<=FREE;
            dst[0]<=0;dst[1]<=0;length[0]<=0;length[1]<=0;mode[0]<=0;mode[1]<=0;
            produced<=0;completed<=0;cycles<=0;overlap_cycles<=0;
            config_ptr<=0;word_index<=0;ps<=P_IDLE;vs<=V_IDLE;
        end else begin
            if(host_reject) rejected<=1;
            if(cfg_we) begin
                if(busy || fault) rejected<=1;
                else case(cfg_addr-BASE)
                    0:if(cfg_wdata==1) begin
                        done<=0;rejected<=0;error_code<=0;
                        if(!valid_batch || !vec_loaded || vec_busy || !vec_idle) begin
                            fault<=1;done<=1;error_code<=1;
                        end else begin
                            busy<=1;cycles<=0;overlap_cycles<=0;produced<=0;completed<=0;
                            slots[0]<=FREE;slots[1]<=FREE;ps<=P_IDLE;vs<=V_IDLE;
                        end
                    end else rejected<=1;
                    8:table_ptr<=cfg_wdata;12:tile_count<=cfg_wdata;
                    16:buffers[0]<=cfg_wdata;20:buffers[1]<=cfg_wdata;
                    24:capacity<=cfg_wdata;28:flags<=cfg_wdata&1;
                    default:rejected<=1;
                endcase
            end
            if(busy && !fault) begin
                cycles<=cycles+1;
                if(conv_busy && vec_busy) overlap_cycles<=overlap_cycles+1;
                case(ps)
                    P_IDLE:if(produced<tile_count && slots[pslot]==FREE &&
                              (!flags[0] || produced==completed)) begin
                        slots[pslot]<=FILL;word_index<=0;ps<=P_DESC;
                    end
                    P_DESC:if(mem_ready) ps<=P_DESC_WAIT;
                    P_DESC_WAIT:if(mem_response) begin
                        case(word_index)
                            0:config_ptr<=mem_rdata;
                            1:dst[pslot]<=mem_rdata;
                            2:length[pslot]<=mem_rdata;
                            3:mode[pslot]<=mem_rdata;
                            default:;
                        endcase
                        if(word_index==3) begin
                            word_index<=0;ps<=P_CONFIG;
                            if(config_ptr[1:0]!=0 || !in_sram(config_ptr,33'd96) ||
                               intersects(config_ptr,33'd96,buffers[0],{1'b0,capacity}) ||
                               intersects(config_ptr,33'd96,buffers[1],{1'b0,capacity})) begin
                                busy<=0;done<=1;fault<=1;error_code<=2;
                            end
                        end else begin word_index<=word_index+1;ps<=P_DESC;end
                    end
                    P_CONFIG:if(mem_ready) ps<=P_CONFIG_WAIT;
                    P_CONFIG_WAIT:if(mem_response) begin
                        image[word_index]<=mem_rdata;
                        if(word_index==23) ps<=P_CHECK;
                        else begin word_index<=word_index+1;ps<=P_CONFIG;end
                    end
                    P_CHECK:if(valid_tile) ps<=P_START;
                        else begin busy<=0;done<=1;fault<=1;error_code<=3;end
                    P_START:ps<=P_RUN;
                    P_RUN:if(conv_done) begin
                        slots[pslot]<=READY;produced<=produced+1;ps<=P_IDLE;
                    end
                    default:ps<=P_IDLE;
                endcase
                case(vs)
                    V_IDLE:if(completed<tile_count && slots[vslot]==READY && !vec_busy && vec_idle) begin
                        slots[vslot]<=DRAIN;vs<=V_SRC;
                    end
                    V_SRC:vs<=V_DST;
                    V_DST:vs<=V_COUNT;
                    V_COUNT:vs<=V_MODE;
                    V_MODE:vs<=V_START;
                    V_START:vs<=V_ACCEPT;
                    // Explicit accept prevents the previous job's sticky done
                    // from releasing a freshly launched slot prematurely.
                    V_ACCEPT:if(vec_busy) vs<=V_RUN;
                    V_RUN:if(vec_done && !vec_busy) vs<=V_DRAIN;
                    V_DRAIN:if(vec_idle) begin
                        slots[vslot]<=FREE;completed<=completed+1;vs<=V_IDLE;
                    end
                    default:vs<=V_IDLE;
                endcase
                if(completed==tile_count && ps==P_IDLE && vs==V_IDLE) begin busy<=0;done<=1;end
                if(conv_error || vec_fault || mem_fault || cycles==MAX_CYCLES-1) begin
                    busy<=0;done<=1;fault<=1;
                    error_code<=conv_error ? 4 : vec_fault ? 5 : mem_fault ? 6 : 7;
                end
            end
        end
    end
endmodule
