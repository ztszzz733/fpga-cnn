`timescale 1ns/1ps
// One independent command/response engine per OPCODE. No shared busy flag.
// Parameter records: signed ma,mb; unsigned sa,sb (0..63); signed zp; limit (0..127).
// ba=0 selects defaults (1,1,0,0,0,96); PReLU requires a record.
module tensor_operator_engine #(parameter OPCODE=6)(
    input wire clk,rst_n,clear,start,input wire [255:0] descriptor,
    output wire busy,done,error,output wire cmd_valid,input wire cmd_ready,
    output wire cmd_write,cmd_byte,output wire [31:0] cmd_addr,cmd_wdata,
    input wire rsp_valid,input wire [31:0] rsp_data);
    localparam IDLE=0,PARAM_REQ=1,PARAM_WAIT=2,A_REQ=3,A_WAIT=4,B_REQ=5,B_WAIT=6,
        CALC=7,WRITE_REQ=8,WRITE_WAIT=9,DONE=10,ERROR=11;
    reg [3:0] state;reg [31:0] ia,oa,wa,ba,fs,ch,lp,index;
    reg [2:0] param_word;reg [1:0] tap;
    reg signed [31:0] a,b,maximum,ma,mb,zp;reg [7:0] sa,sb,limit;
    reg signed [7:0] output_value;
    wire [31:0] aa,ab,ao,ap,count,channel_end;
    tensor_address_generator addresses(ia,oa,wa,ba,fs,ch,lp,OPCODE[3:0],index,tap,aa,ab,ao,ap,count,channel_end);
    wire signed [63:0] scaled_a,scaled_b,added,prelu,activated;
    fixed_scale_unit scale_a(a,ma,sa,lp[22],scaled_a);
    fixed_scale_unit scale_b(b,mb,sb,lp[22],scaled_b);
    residual_add_unit add(scaled_a,scaled_b,added);
    prelu_unit prelu_math(a,scaled_a,prelu);
    wire signed [63:0] raw=OPCODE==3 ? added : (OPCODE==7 ? prelu : (OPCODE==10 ? scaled_a : {{32{a[31]}},a}));
    wire signed [63:0] biased=raw+{{32{zp[31]}},zp};
    wire signed [63:0] shifted=biased >>> lp[19:12];
    activation_unit activation(shifted,OPCODE==2,limit,activated);
    wire signed [7:0] quantized;
    requantize_unit quant((OPCODE==2 || OPCODE==6) ? activated : shifted,8'd0,quantized);
    wire signed [31:0] pool_next, pool_sample;
    assign pool_sample = rsp_data;
    maxpool_unit pool(pool_sample,maximum,tap==0,pool_next);
    assign busy=state!=IDLE && state!=DONE && state!=ERROR;
    assign done=state==DONE;assign error=state==ERROR;
    assign cmd_valid=!clear && (state==PARAM_REQ || state==A_REQ || state==B_REQ || state==WRITE_REQ);
    assign cmd_write=state==WRITE_REQ;
    assign cmd_byte=state!=PARAM_REQ && !(state==A_REQ && OPCODE==10 && lp[20]);
    assign cmd_addr=state==PARAM_REQ ? ap+{27'd0,param_word,2'b00} : (state==B_REQ ? ab : (state==WRITE_REQ ? ao : aa));
    assign cmd_wdata={24'd0,output_value};
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;ia<=0;oa<=0;wa<=0;ba<=0;fs<=0;ch<=0;lp<=0;index<=0;
            param_word<=0;tap<=0;a<=0;b<=0;maximum<=0;ma<=1;mb<=1;sa<=0;sb<=0;zp<=0;limit<=96;output_value<=0;
        end else if(clear) begin state<=IDLE;index<=0;tap<=0;param_word<=0;end
        else case(state)
            IDLE:if(start) begin
                ia<=descriptor[63:32];oa<=descriptor[95:64];wa<=descriptor[127:96];ba<=descriptor[159:128];
                fs<=descriptor[191:160];ch<=descriptor[223:192];lp<=descriptor[255:224];
                index<=0;tap<=0;param_word<=0;b<=0;ma<=1;mb<=1;sa<=0;sb<=0;zp<=0;limit<=96;
                state<=descriptor[159:128]!=0 ? PARAM_REQ : A_REQ;
            end
            PARAM_REQ:if(cmd_ready) state<=PARAM_WAIT;
            PARAM_WAIT:if(rsp_valid) begin
                case(param_word)
                    0:ma<=rsp_data;1:mb<=rsp_data;2:sa<=rsp_data[7:0];3:sb<=rsp_data[7:0];4:zp<=rsp_data;5:limit<=rsp_data[7:0];
                endcase
                if(((param_word==2 || param_word==3) && rsp_data>63) || (param_word==5 && rsp_data>127)) state<=ERROR;
                else if(param_word==5) state<=A_REQ;
                else begin param_word<=param_word+1'b1;state<=PARAM_REQ;end
            end
            A_REQ:if(cmd_ready) state<=A_WAIT;
            A_WAIT:if(rsp_valid) begin
                if(OPCODE==8) begin
                    maximum<=pool_next;
                    if(tap==3) begin a<=pool_next;tap<=0;state<=CALC;end
                    else begin tap<=tap+1'b1;state<=A_REQ;end
                end else begin a<=rsp_data;state<=OPCODE==3 ? B_REQ : CALC;end
            end
            B_REQ:if(cmd_ready) state<=B_WAIT;
            B_WAIT:if(rsp_valid) begin b<=rsp_data;state<=CALC;end
            CALC:begin output_value<=quantized;state<=WRITE_REQ;end
            WRITE_REQ:if(cmd_ready) state<=WRITE_WAIT;
            WRITE_WAIT:if(rsp_valid) begin
                if(index+1==count) state<=DONE;
                else begin
                    index<=index+1;tap<=0;
                    if(ba!=0 && lp[21] && index+1==channel_end) begin param_word<=0;state<=PARAM_REQ;end
                    else state<=A_REQ;
                end
            end
            DONE:state<=IDLE;ERROR:state<=IDLE;default:state<=IDLE;
        endcase
    end
endmodule
