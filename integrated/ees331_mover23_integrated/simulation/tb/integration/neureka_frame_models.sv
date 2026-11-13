// TEST ONLY. Scalar functional models, not the pinned NEureka/Vicuna cores.
// They exercise real config/SRAM requests and match only this INT8 demo shape.
module neureka_conv_engine (
    input logic clk,rst_n,clear,start,input logic [31:0] config_address,
    output wire busy,output logic done,error,
    output wire cfg_valid,output wire [31:0] cfg_addr,
    input logic cfg_ready,cfg_response,input logic [31:0] cfg_rdata,
    output logic [8:0] valid,write,byte_access,output logic [287:0] addr,wdata,
    input wire [8:0] ready,response,input wire [287:0] rdata,
    output wire core_busy,memory_idle
);
    typedef enum logic [3:0] {IDLE,CFG,CFG_WAIT,WEIGHTS,WEIGHTS_WAIT,
        INPUT_BYTE,INPUT_WAIT,OUTPUT_BYTE,OUTPUT_WAIT,HOLD} state_t;
    state_t state;
    logic [31:0] cfg[0:23],weights[0:359];
    integer ci,co,oh,ow,ic,oc,x,y,ky,kx,idx,wi,acc,value,weight_value;
    integer hold_count,conv_delay=20000;
    initial if(!$value$plusargs("CONV_DELAY=%d",conv_delay)) conv_delay=20000;
    assign busy=state!=IDLE;assign core_busy=busy;assign memory_idle=state==IDLE;
    assign cfg_valid=state==CFG;assign cfg_addr=config_address+idx*4;
    always_comb begin
        valid=0;write=0;byte_access=0;addr=0;wdata=0;
        case(state)
            WEIGHTS:begin valid[0]=1;addr[31:0]=cfg[0]+wi*4;end
            INPUT_BYTE:begin
                valid[0]=1;byte_access[0]=1;
                addr[31:0]=cfg[1]+(y+ky)*cfg[7]+(x+kx)*cfg[6]+ic;
            end
            OUTPUT_BYTE:begin
                valid[0]=1;write[0]=1;byte_access[0]=1;
                addr[31:0]=cfg[2]+(y*ow+x)*co+oc;wdata[31:0]=value&255;
            end
            default:;
        endcase
    end
    always @(posedge clk) begin
        done<=0;
        if(!rst_n || clear) begin state<=IDLE;error<=0;idx<=0;wi<=0;acc<=0;end
        else case(state)
            IDLE:if(start) begin idx<=0;state<=CFG;end
            CFG:if(cfg_ready) state<=CFG_WAIT;
            CFG_WAIT:if(cfg_response) begin
                cfg[idx]<=cfg_rdata;
                if(idx==23) begin wi<=0;state<=WEIGHTS;end
                else begin idx<=idx+1;state<=CFG;end
            end
            WEIGHTS:if(ready[0]) state<=WEIGHTS_WAIT;
            WEIGHTS_WAIT:if(response[0]) begin
                weights[wi]<=rdata[31:0];
                if(wi==359) begin
                    ci=cfg[6];co=cfg[10];
                    ow=((cfg[19]&65535)-1)*4+(cfg[16]&65535);
                    oh=((cfg[19]>>16)-1)*4+(cfg[16]>>16);
                    if(ci!=3 || co!=5 || ow!=7 || oh<1 || oh>4) $fatal(1,"unsupported scalar model shape");
                    ic<=0;oc<=0;x<=0;y<=0;ky<=0;kx<=0;acc<=0;hold_count<=conv_delay;state<=HOLD;
                end else begin wi<=wi+1;state<=WEIGHTS;end
            end
            HOLD:if(hold_count==0) state<=INPUT_BYTE;else hold_count<=hold_count-1;
            INPUT_BYTE:if(ready[0]) state<=INPUT_WAIT;
            INPUT_WAIT:if(response[0]) begin
                weight_value=0;
                for(integer bit_index=0;bit_index<8;bit_index++)
                    weight_value=weight_value|(((weights[(oc*8+bit_index)*9+ky*3+kx]>>ic)&1)<<bit_index);
                weight_value=weight_value-128;
                acc=acc+(rdata[7:0]*weight_value);
                if(ic==ci-1 && kx==2 && ky==2) begin
                    value=acc>>>((cfg[23]>>16)&31);
                    if(value>127) value=127;
                    if(value< -128) value=-128;
                    state<=OUTPUT_BYTE;
                end else begin
                    if(ic==ci-1) begin
                        ic<=0;if(kx==2) begin kx<=0;ky<=ky+1;end else kx<=kx+1;
                    end else ic<=ic+1;
                    state<=INPUT_BYTE;
                end
            end
            OUTPUT_BYTE:if(ready[0]) state<=OUTPUT_WAIT;
            OUTPUT_WAIT:if(response[0]) begin
                if(oc==co-1 && x==ow-1 && y==oh-1) begin state<=IDLE;done<=1;end
                else begin
                    acc<=0;ic<=0;kx<=0;ky<=0;
                    if(oc==co-1) begin oc<=0;if(x==ow-1) begin x<=0;y<=y+1;end else x<=x+1;end
                    else oc<=oc+1;
                    state<=INPUT_BYTE;
                end
            end
            default:state<=IDLE;
        endcase
    end
endmodule

module vicuna_programmable #(
    parameter logic [31:0] BASE=32'h40040000,SRAM_BASE=0,SRAM_SIZE=32'h40000,
    parameter integer PROGRAM_BYTES=16384,MAX_CYCLES=200000
)(
    input logic clk,rst_n,
    input logic [31:0] cfg_addr,cfg_wdata,input logic cfg_re,cfg_we,
    output logic [31:0] cfg_rdata,output wire cfg_ready,
    output wire mem_valid,mem_write,mem_byte,
    output wire [31:0] mem_addr,mem_wdata,
    input logic mem_ready,mem_response,input logic [31:0] mem_rdata,
    input logic mem_fault,
    output wire busy,output logic done,output wire fault,output wire [31:0] result_code,
    output logic [31:0] cycles,jobs,output wire [2:0] memory_state,
    output logic [31:0] reads,writes,stalls,output wire [31:0] pending_registers
);
    typedef enum logic [2:0] {IDLE,READ_BYTE,READ_WAIT,WRITE_BYTE,WRITE_WAIT} state_t;
    state_t state;
    logic [31:0] src,dst,count,index;
    integer value;
    assign busy=state!=IDLE;assign fault=mem_fault;assign result_code=0;assign cfg_ready=1;
    assign memory_state=state;assign pending_registers=busy ? 1 : 0;
    assign mem_valid=state==READ_BYTE || state==WRITE_BYTE;
    assign mem_write=state==WRITE_BYTE;assign mem_byte=1;
    assign mem_addr=(mem_write ? dst : src)+index;assign mem_wdata=value&255;
    always_comb cfg_rdata=cfg_addr==BASE ? {30'b0,done,busy} : 0;
    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;done<=0;cycles<=0;jobs<=0;reads<=0;writes<=0;stalls<=0;
            src<=0;dst<=0;count<=0;index<=0;value<=0;
        end else begin
            if(busy) cycles<=cycles+1;
            if(mem_valid && !mem_ready) stalls<=stalls+1;
            if(cfg_we) case(cfg_addr-BASE)
                4:src<=cfg_wdata;
                8:dst<=cfg_wdata;
                12:count<=cfg_wdata;
                0:if(cfg_wdata==1) begin
                    if(busy || count==0) $fatal(1,"invalid vector model start");
                    done<=0;index<=0;cycles<=0;state<=READ_BYTE;
                end
                default:;
            endcase
            case(state)
                READ_BYTE:if(mem_ready) begin reads<=reads+1;state<=READ_WAIT;end
                READ_WAIT:if(mem_response) begin
                    value=$signed(mem_rdata);if(value<0) value=value>>>2;state<=WRITE_BYTE;
                end
                WRITE_BYTE:if(mem_ready) begin writes<=writes+1;state<=WRITE_WAIT;end
                WRITE_WAIT:if(mem_response) begin
                    if(index==count-1) begin state<=IDLE;done<=1;jobs<=jobs+1;end
                    else begin index<=index+1;state<=READ_BYTE;end
                end
                default:;
            endcase
        end
    end
endmodule
