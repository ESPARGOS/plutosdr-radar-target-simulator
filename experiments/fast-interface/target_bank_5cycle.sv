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
 output reg [31:0] sample_count
);
 localparam DEPTH=1<<AW;
 reg [AW-1:0] wr;
 reg [AW:0] filled;
 reg [4:0] valid_pipe;
 wire signed [32:0] products_i [0:N-1], products_q [0:N-1];
 wire signed [17:0] rotated_i [0:N-1], rotated_q [0:N-1];
 integer k;
 reg signed [22:0] sum_i, sum_q;
 always @* begin
   sum_i=0; sum_q=0;
   for(integer j=0;j<N;j=j+1) begin
     sum_i=sum_i+$signed(rotated_i[j]);
     sum_q=sum_q+$signed(rotated_q[j]);
   end
 end
 function automatic signed [15:0] saturate(input signed [22:0] x);
   if(x>32767) saturate=32767;
   else if(x< -32768) saturate=-32768;
   else saturate=x[15:0];
 endfunction
 always @(posedge clk) begin
   if(reset) begin
     wr<=0; filled<=0; valid_pipe<=0; out_valid<=0;
     out_i<=0;out_q<=0;clipped<=0;sample_count<=0;
   end else begin
     if(sample_valid) begin
       wr<=wr+1'b1;
       if(filled<DEPTH) filled<=filled+1'b1;
       sample_count<=sample_count+1'b1;
     end
     valid_pipe<={valid_pipe[3:0],sample_valid};
     out_valid<=valid_pipe[4];
     if(valid_pipe[4]) begin
       out_i<=saturate(sum_i);out_q<=saturate(sum_q);
       if(sum_i>32767 || sum_i< -32768 || sum_q>32767 || sum_q< -32768) clipped<=1;
     end
     // Drop all in-flight samples when an atomic configuration is applied.
     if(configure) begin
       valid_pipe<=0;out_valid<=0;out_i<=0;out_q<=0;clipped<=0;
     end
   end
 end
 generate for(genvar t=0;t<N;t=t+1) begin: target
   (* ram_style="block" *) reg [31:0] history [0:DEPTH-1];
   reg [31:0] phase;
   wire [AW-1:0] delay_samples=delays[t*AW+:AW];
   wire [AW-1:0] rd=wr-delay_samples;
   reg [31:0] read_data;
   reg signed [15:0] data_i,data_q,data_i2,data_q2;
   reg signed [17:0] rotated_i_reg,rotated_q_reg;
   assign rotated_i[t]=rotated_i_reg;
   assign rotated_q[t]=rotated_q_reg;
   reg signed [15:0] cosine,sine;
   reg [15:0] gain0,gain1;
   reg [31:0] trig1;
   reg signed [31:0] ic,qs,is_,qc;

   reg active0;
   reg [31:0] direct_data;
   reg direct;
   reg [9:0] phase_index;
   wire [31:0] trig;
   wire signed [32:0] scaled_cosine=$signed(trig1[15:0])*$signed({1'b0,gain1});
   wire signed [32:0] scaled_sine=$signed(trig1[31:16])*$signed({1'b0,gain1});
   nco_rom rom(.addr(phase_index),.data(trig));
   assign products_i[t]=$signed({ic[31],ic})-$signed({qs[31],qs});
   assign products_q[t]=$signed({is_[31],is_})+$signed({qc[31],qc});
   // The history RAM has a synchronous read and no reset, allowing BRAM inference.
   always @(posedge clk) if(sample_valid) begin
     history[wr]<={sample_q,sample_i};
     read_data<=history[rd];
   end
   always @(posedge clk) begin
     if(reset) begin
       phase<=0;active0<=0;direct<=0;direct_data<=0;phase_index<=0;
       data_i<=0;data_q<=0;cosine<=0;sine<=0;
       gain0<=0;gain1<=0;trig1<=0;data_i2<=0;data_q2<=0;rotated_i_reg<=0;rotated_q_reg<=0;
       ic<=0;qs<=0;is_<=0;qc<=0;
     end else begin
       // Stage 0: synchronous history read; phase advances once per input sample.
       if(sample_valid) begin
         phase<=phase+increments[t*32+:32];
         phase_index<=phase[31:22];
         direct_data<={sample_q,sample_i}; direct<=(delay_samples==0);
         active0<=enabled[t] && filled>=delay_samples;
         gain0<=gains[t*16+:16];
       end
       // Stage 1: capture ROM output and align the history read.
       // Stage 2: scale oscillator coefficients by gain and delay IQ.
       data_i<=active0 ? (direct ? direct_data[15:0] : read_data[15:0]) : 16'd0;
       data_q<=active0 ? (direct ? direct_data[31:16] : read_data[31:16]) : 16'd0;
       trig1<=trig;gain1<=gain0;
       data_i2<=data_i;data_q2<=data_q;
       cosine<=scaled_cosine >>> 15;
       sine<=scaled_sine >>> 15;
       // Stage 3: complex multiplication; stage 4: per-target rotation.
       // Stage 5 sums and saturates all targets.
       ic<=data_i2*cosine; qs<=data_q2*sine;
       is_<=data_i2*sine; qc<=data_q2*cosine;
       rotated_i_reg<=$signed(products_i[t]) >>> 15;
       rotated_q_reg<=$signed(products_q[t]) >>> 15;
       if(configure && restart) phase<=0;
     end
   end
 end endgenerate
endmodule
