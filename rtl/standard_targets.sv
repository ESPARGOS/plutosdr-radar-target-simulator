// Four standard_targets share the interpolation and complex rotation pipelines.
// All inputs except the oscillator-table write port use the processing clock.
module standard_targets(input wire clk, reset, valid,
 input wire [23:0] sample,
 input wire [55:0] delays,
 input wire [39:0] fractions, phases,
 input wire [3:0] enabled,
 input wire active_table, muted,
 input wire table_clk, table_write,
 input wire [12:0] table_address,
 input wire [31:0] table_data,
 output reg [15:0] out_i,out_q,
 output reg out_valid,out_table,clipped);
wire [31:0] direct_sample,interpolated_sample;
wire up_valid;
standard_upsample up(clk,reset,valid,sample,direct_sample,interpolated_sample,up_valid);
localparam META=142;
wire [META-1:0] metadata={muted,active_table,enabled,phases,fractions,delays};
reg [META-1:0] meta[0:8];
reg [META-1:0] saved;
reg [1:0] slot;
reg scheduling;
reg [14:0] pointer,reference;
reg [15:0] filled,filled_plus_one,reference_filled;
reg pending;
reg [31:0] direct_pending;
wire write_enable=up_valid || pending;
wire [31:0] write_data=up_valid ? interpolated_sample : direct_pending;
wire request_valid=up_valid || scheduling;
wire [1:0] target=up_valid ? 2'd0 : slot;
wire [META-1:0] selected=up_valid ? meta[8] : saved;
wire [13:0] delay=selected[target*14+:14];
wire [9:0] fraction=selected[56+target*10+:10];
wire [9:0] phase=selected[96+target*10+:10];
wire echo_enabled=selected[136+target] && !selected[141];
wire bank=selected[140];
wire [14:0] distance={delay,fraction[9]};
wire [14:0] position=up_valid ? pointer : reference;
wire [15:0] available_count=up_valid ? filled_plus_one : reference_filled;
reg [14:0] read_address,read_address_pipe;
reg signed [16:0] history_distance;
reg [9:0] mu,mu_delayed,mu_pipe[0:3];
reg [7:0] available;
wire [255:0] samples;
wire [75:0] result;
reg [13:0] valid_pipe,en_pipe,bank_pipe;
reg [1:0] tags[0:13];
(* ram_style="block" *) reg [31:0] oscillator[0:8191];
reg [12:0] trig_address;
reg [31:0] trig,trig_pipe[0:11];
always @(posedge table_clk)
 if(table_write) oscillator[table_address]<=table_data;
always @(posedge clk) begin
 meta[0]<=metadata;
 for(integer k=1;k<9;k=k+1) meta[k]<=meta[k-1];
 pending<=!reset && up_valid;
 direct_pending<=direct_sample;
 if(write_enable) begin
  pointer<=pointer+1'b1;
  if(filled<32768) filled<=filled+1'b1;
  if(filled_plus_one<32768) filled_plus_one<=filled_plus_one+1'b1;
 end
 if(up_valid) begin saved<=meta[8];reference<=pointer;reference_filled<=available_count;slot<=1;scheduling<=1;end
 else if(scheduling) begin slot<=slot+1'b1;if(slot==3) scheduling<=0;end
 read_address<=position-distance;
 mu<={fraction[8:0],1'b0};
 history_distance<=$signed({1'b0,available_count})-$signed({2'b00,distance});
 read_address_pipe<=read_address;mu_delayed<=mu;
 for(integer k=0;k<8;k=k+1) available[k]<=history_distance>k;
 mu_pipe[0]<=mu_delayed;mu_pipe[1]<=mu_pipe[0];mu_pipe[2]<=mu_pipe[1];mu_pipe[3]<=mu_pipe[2];
 valid_pipe<={valid_pipe[12:0],request_valid};
 en_pipe<={en_pipe[12:0],echo_enabled};
 bank_pipe<={bank_pipe[12:0],bank};
 tags[0]<=target;for(integer k=1;k<14;k=k+1) tags[k]<=tags[k-1];
 trig_address<={bank,target,phase};
 trig<=oscillator[trig_address];
 trig_pipe[0]<=trig;for(integer k=1;k<12;k=k+1) trig_pipe[k]<=trig_pipe[k-1];
 if(reset) begin pointer<=0;filled<=0;filled_plus_one<=1;pending<=0;scheduling<=0;valid_pipe<=0;end
end
standard_history mem(clk,write_enable && !reset,pointer,read_address_pipe,write_data,available,samples);
standard_fir fir(clk,samples,mu_pipe[3],result);
wire signed [37:0] rounded_i=$signed(result[37:0])+38'sd8192;
wire signed [37:0] rounded_q=$signed(result[75:38])+38'sd8192;
(* DONT_TOUCH="TRUE" *) reg signed [19:0] delayed_i,delayed_q;
reg normalized_valid,normalized_enabled,normalized_bank;
reg [1:0] normalized_tag;
reg [31:0] normalized_trig;
always @(posedge clk) begin
 delayed_i<=rounded_i>>>14;delayed_q<=rounded_q>>>14;
 normalized_valid<=valid_pipe[13];normalized_enabled<=en_pipe[13];
 normalized_bank<=bank_pipe[13];normalized_tag<=tags[13];normalized_trig<=trig_pipe[11];
 if(reset || muted) normalized_valid<=0;
end
reg signed [19:0] data_i,data_q;
reg signed [20:0] data_sum;
reg signed [15:0] cosine;
reg signed [16:0] trig_sum,trig_difference;
(* use_dsp="yes" *) reg signed [36:0] common_product,cross_i,cross_q;
reg signed [36:0] common_delay,cross_delay_i,cross_delay_q;
reg signed [37:0] rotated_i,rotated_q;
reg [3:0] rotate_valid,rotate_bank;
reg [1:0] rotate_tag[0:3];
reg signed [24:0] accumulated_i,accumulated_q,final_i,final_q;
reg final_valid,final_bank;
wire signed [22:0] echo_i=rotated_i>>>15,echo_q=rotated_q>>>15;
reg clip_valid,clip_bank,clip_i,clip_q,sign_i,sign_q;
reg [15:0] raw_i,raw_q;
always @(posedge clk) begin
 data_i<=normalized_enabled ? delayed_i : 20'sd0;
 data_q<=normalized_enabled ? delayed_q : 20'sd0;
 data_sum<=normalized_enabled ? $signed(delayed_i)+$signed(delayed_q) : 21'sd0;
 cosine<=normalized_enabled ? normalized_trig[15:0] : 16'd0;
 trig_sum<=normalized_enabled ? $signed(normalized_trig[15:0])+$signed(normalized_trig[31:16]) : 17'sd0;
 trig_difference<=normalized_enabled ? $signed(normalized_trig[31:16])-$signed(normalized_trig[15:0]) : 17'sd0;
 common_product<=data_sum*cosine; cross_i<=data_q*trig_sum;cross_q<=data_i*trig_difference;
 common_delay<=common_product;cross_delay_i<=cross_i;cross_delay_q<=cross_q;
 rotated_i<=$signed(common_delay)-$signed(cross_delay_i);
 rotated_q<=$signed(common_delay)+$signed(cross_delay_q);
 rotate_valid<={rotate_valid[2:0],normalized_valid};
 rotate_bank<={rotate_bank[2:0],normalized_bank};
 rotate_tag[0]<=normalized_tag;for(integer k=1;k<4;k=k+1) rotate_tag[k]<=rotate_tag[k-1];
 final_valid<=rotate_valid[3] && rotate_tag[3]==3;
 if(rotate_valid[3]) begin
  if(rotate_tag[3]==0) begin accumulated_i<=echo_i;accumulated_q<=echo_q;end
  else begin accumulated_i<=accumulated_i+echo_i;accumulated_q<=accumulated_q+echo_q;end
  if(rotate_tag[3]==3) begin final_i<=accumulated_i+echo_i;final_q<=accumulated_q+echo_q;final_bank<=rotate_bank[3];end
 end
 clip_valid<=final_valid;
 if(final_valid) begin
  clip_i<=final_i[24:15]!={10{final_i[15]}};
  clip_q<=final_q[24:15]!={10{final_q[15]}};
  sign_i<=final_i[24];sign_q<=final_q[24];
  raw_i<=final_i[15:0];raw_q<=final_q[15:0];clip_bank<=final_bank;
 end
 out_valid<=clip_valid;
 if(clip_valid) begin
  out_i<=clip_i ? (sign_i ? 16'h8000 : 16'h7fff) : raw_i;
  out_q<=clip_q ? (sign_q ? 16'h8000 : 16'h7fff) : raw_q;
  out_table<=clip_bank;
  if(clip_bank!=out_table) clipped<=clip_i || clip_q;
  else if(clip_i || clip_q) clipped<=1;
 end
 if(reset || muted) begin rotate_valid<=0;final_valid<=0;clip_valid<=0;out_valid<=0;out_i<=0;out_q<=0;clipped<=0;end
end
endmodule
