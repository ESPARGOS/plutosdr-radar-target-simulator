// Four parallel delay/Doppler paths. Signed 16-bit IQ; gain and NCO use Q1.15.
module target_bank #(parameter N=4, parameter AW=11)(
 input wire clk, reset, configure, restart,
 input wire sample_valid, input wire signed [15:0] sample_i, sample_q,
 input wire [N-1:0] enabled,
 input wire [N*AW-1:0] delays,
 input wire [N*32-1:0] increments,
 input wire [N*16-1:0] gains,
 output reg signed [15:0] out_i, out_q,
 output reg out_valid, output reg clipped,
 output wire reload_busy,
 output reg [31:0] sample_count
);
 localparam DEPTH=1<<AW;
 reg [AW-1:0] wr;
 reg [AW:0] filled;
 reg [2:0] valid_pipe;
 // Coefficients depend only on target settings, not incoming RF samples.
 // Build four gain-scaled ROMs after each commit, then read them alongside IQ.
 // This preserves the exact existing Q1.15 arithmetic and 10-bit NCO table.
 reg preparing,prepared,active_table,settle,pending_restart;
 reg [N-1:0] active_enabled;
 reg [N*AW-1:0] active_delays;
 reg [N*32-1:0] active_increments;
 reg [10:0] prepare_count;
 wire [9:0] write_index=prepare_count-2'd2;
 wire activate=preparing && prepare_count==1026 && !configure;
 wire mute_now=configure && enabled==0;
 wire flush=activate || mute_now;
 assign reload_busy=preparing || settle;
 wire [31:0] prepare_trig;
 reg [31:0] prepare_trig_pipe;
 always @(posedge clk) if(preparing && !configure) prepare_trig_pipe<=prepare_trig;
 nco_rom prepare_rom(.addr(prepare_count[9:0]),.data(prepare_trig));
 always @(posedge clk) begin
   if(reset) begin
     preparing<=0;prepared<=0;prepare_count<=0;active_table<=0;settle<=0;
     active_enabled<=0;active_delays<=0;active_increments<=0;pending_restart<=0;
   end else if(configure) begin
     prepare_count<=0;pending_restart<=restart;
     if(enabled==0) begin
       preparing<=0;prepared<=0;settle<=0;active_enabled<=0;
       active_delays<=delays;active_increments<=increments;
     end else preparing<=1;
   end else if(activate) begin
     // Swap complete tables atomically; the previous scene ran throughout reload.
     preparing<=0;prepared<=0;settle<=1;active_table<=~active_table;
     active_enabled<=enabled;active_delays<=delays;active_increments<=increments;
   end else begin
     if(preparing) prepare_count<=prepare_count+1'b1;
     if(settle) begin settle<=0;prepared<=1;end
   end
 end
 wire signed [32:0] products_i [0:N-1], products_q [0:N-1];
 wire signed [17:0] rotated_i [0:N-1], rotated_q [0:N-1];
 integer k;
 localparam SUM_W=18+$clog2(N);
 localparam PAIRS=(N+1)/2;
 wire signed [18:0] pair_i [0:PAIRS-1],pair_q [0:PAIRS-1];
 generate for(genvar p=0;p<PAIRS;p=p+1) begin: combine
   if(2*p+1<N) begin
     assign pair_i[p]=$signed(rotated_i[2*p])+$signed(rotated_i[2*p+1]);
     assign pair_q[p]=$signed(rotated_q[2*p])+$signed(rotated_q[2*p+1]);
   end else begin
     assign pair_i[p]=$signed(rotated_i[2*p]);assign pair_q[p]=$signed(rotated_q[2*p]);
   end
 end endgenerate
 reg signed [18:0] pair_pipe_i [0:PAIRS-1],pair_pipe_q [0:PAIRS-1];
 always @(posedge clk) begin
   for(integer j=0;j<PAIRS;j=j+1) begin
     pair_pipe_i[j]<=pair_i[j];pair_pipe_q[j]<=pair_q[j];
   end
 end
 reg signed [SUM_W-1:0] sum_i,sum_q;
 always @* begin
   sum_i=0;sum_q=0;
   for(integer j=0;j<PAIRS;j=j+1) begin
     sum_i=sum_i+$signed(pair_pipe_i[j]);sum_q=sum_q+$signed(pair_pipe_q[j]);
   end
 end
 wire overflow_i=sum_i[SUM_W-1:15]!={(SUM_W-15){sum_i[15]}};
 wire overflow_q=sum_q[SUM_W-1:15]!={(SUM_W-15){sum_q[15]}};
 reg overflow_pending_i,overflow_pending_q;
 function automatic signed [15:0] saturate(input signed [SUM_W-1:0] x);
   if(x[SUM_W-1:15]=={(SUM_W-15){x[15]}}) saturate=x[15:0];
   else saturate=x[SUM_W-1] ? 16'sh8000 : 16'sd32767;
 endfunction
 always @(posedge clk) begin
   if(reset) begin
     wr<=0; filled<=0; valid_pipe<=0; out_valid<=0;
     out_i<=0;out_q<=0;clipped<=0;sample_count<=0;overflow_pending_i<=0;overflow_pending_q<=0;
   end else begin
     if(sample_valid) begin
       wr<=wr+1'b1;
       if(filled<DEPTH) filled<=filled+1'b1;
       sample_count<=sample_count+1'b1;
     end
     valid_pipe<={valid_pipe[1:0],sample_valid && prepared};
     out_valid<=valid_pipe[2];
     overflow_pending_i<=valid_pipe[2] && overflow_i;
     overflow_pending_q<=valid_pipe[2] && overflow_q;
     if(overflow_pending_i || overflow_pending_q) clipped<=1;
     if(valid_pipe[2]) begin
       out_i<=saturate(sum_i);out_q<=saturate(sum_q);
     end
     // Drop all in-flight samples when an atomic configuration is applied.
     if(flush) begin
       valid_pipe<=0;out_valid<=0;out_i<=0;out_q<=0;clipped<=0;
       overflow_pending_i<=0;overflow_pending_q<=0;
     end
   end
 end
 generate for(genvar t=0;t<N;t=t+1) begin: target
   (* ram_style="block" *) reg [31:0] history [0:DEPTH-1];
   (* ram_style="block" *) reg [31:0] coefficients [0:2047];
   reg [31:0] phase;
   wire [AW-1:0] delay_samples=active_delays[t*AW+:AW];
   // Prefetch exactly the history location needed by the next clock edge.
   // This uses only already received samples; delay 0/1 have direct bypasses.
   reg [AW-1:0] read_pointer,pending_pointer;
   reg configured_valid;
   wire [1:0] initial_advance=2'd1+configured_valid+sample_valid;
   wire [AW-1:0] rd=read_pointer+sample_valid;
   // Track each history pointer instead of subtracting delay on every RAM read.
   // During reload, initialize a spare pointer in two short arithmetic steps.
   always @(posedge clk) begin
     if(reset) begin read_pointer<=0;pending_pointer<=0;configured_valid<=0;end
     else begin
       if(configure) begin
         pending_pointer<=wr+~delays[t*AW+:AW];configured_valid<=sample_valid;
       end else if(preparing && prepare_count==0)
         pending_pointer<=pending_pointer+initial_advance;
       else if(sample_valid) pending_pointer<=pending_pointer+1'b1;
       if(activate) read_pointer<=pending_pointer+sample_valid;
       else if(sample_valid) read_pointer<=read_pointer+1'b1;
     end
   end
   wire [31:0] next_phase=phase+(sample_valid ? active_increments[t*32+:32] : 32'd0);
   reg [31:0] read_data,last_data,trig;
   reg signed [32:0] prepare_cosine,prepare_sine;
   // Preserve the explicit CDC capture register, then let the DSP absorb this
   // local gain register. Gains are stable before the first table entry writes.
   reg signed [16:0] prepare_gain;
   always @(posedge clk) prepare_gain<=$signed({1'b0,gains[t*16+:16]});
   wire signed [15:0] data_i=(active_enabled[t] && filled>=delay_samples) ?
     (delay_samples==0 ? sample_i : delay_samples==1 ? last_data[15:0] : read_data[15:0]) : 16'd0;
   wire signed [15:0] data_q=(active_enabled[t] && filled>=delay_samples) ?
     (delay_samples==0 ? sample_q : delay_samples==1 ? last_data[31:16] : read_data[31:16]) : 16'd0;
   reg signed [31:0] ic,qs,is_,qc;
   reg signed [15:0] data_i1,data_q1;
   reg [31:0] trig1;
   assign rotated_i[t]=$signed(products_i[t]) >>> 15;
   assign rotated_q[t]=$signed(products_q[t]) >>> 15;
   assign products_i[t]=$signed({ic[31],ic})-$signed({qs[31],qs});
   assign products_q[t]=$signed({is_[31],is_})+$signed({qc[31],qc});
   // No array resets: both tables infer block RAM, with synchronous reads.
   // Reload the inactive table while the active table continues producing IQ.
   always @(posedge clk) begin
     if(sample_valid) begin
       history[wr]<={sample_q,sample_i};
     end
     if(sample_valid || settle) read_data<=history[rd];
     trig<=coefficients[{active_table,next_phase[31:22]}];
     if(preparing && !configure) begin
       prepare_cosine<=$signed(prepare_trig_pipe[15:0])*prepare_gain;
       prepare_sine<=$signed(prepare_trig_pipe[31:16])*prepare_gain;
       if(prepare_count>=2 && prepare_count<=1025)
         coefficients[{~active_table,write_index}]<={prepare_sine[30:15],prepare_cosine[30:15]};
     end
   end
   always @(posedge clk) begin
     if(reset) begin
       phase<=0;last_data<=0;
       data_i1<=0;data_q1<=0;trig1<=0;
       ic<=0;qs<=0;is_<=0;qc<=0;
     end else begin
       // Reads are prefetched one edge ahead, including across sample-valid gaps.
       if(sample_valid) begin
         phase<=phase+active_increments[t*32+:32];
         last_data<={sample_q,sample_i};
       end
       // Stage 0: register current/past IQ with the matching prefetched coefficient.
       // Stage 1: multipliers. Stage 2: rotation/pair sum. Stage 3: sum/saturate.
       data_i1<=data_i;data_q1<=data_q;trig1<=trig;
       ic<=data_i1*$signed(trig1[15:0]);qs<=data_q1*$signed(trig1[31:16]);
       is_<=data_i1*$signed(trig1[31:16]);qc<=data_q1*$signed(trig1[15:0]);
       if((activate && pending_restart) || (mute_now && restart)) phase<=0;
     end
   end
 end endgenerate
endmodule
