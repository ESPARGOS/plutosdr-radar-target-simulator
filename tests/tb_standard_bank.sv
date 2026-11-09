module tb;
parameter CORE_OFFSET=0;
reg clk=0,core_clk=1;
always #20 clk=~clk;
initial begin #CORE_OFFSET;forever #5 core_clk=~core_clk;end
reg core_locked=1,reset=1,configure=0,restart=0,sample_valid=0,fast_profile=0,scene_muted=1;
reg signed [15:0] sample_i=0,sample_q=0;
reg [3:0] enabled=0,moving=0,position_edits=15,velocity_edits=15;
reg [55:0] delays=0;
reg [63:0] fractions=0,gains={4{16'd4096}};
reg [127:0] increments={4{32'd1234567}};
reg [191:0] delay_steps=0;
reg [13:0] upper=12276;
wire signed [15:0] out_i,out_q;
wire out_valid,clipped,reload_busy;
wire [31:0] sample_count;
wire [55:0] current_delays;
wire [63:0] current_fractions;
wire [127:0] current_increments;
standard_bank dut(.*);
reg [165:0] inputs[0:16383];
reg [33:0] outputs[0:16383];
integer iw=0,ir=0,ow=0,orr=0,n,seed=12345;
always @(posedge clk) begin
 #1;
 if(!reset && sample_valid) begin inputs[iw]=dut.input_mailbox;iw=iw+1;end
 if(configure && scene_muted) orr=ow;
 if(!reset && scene_muted && (out_valid || out_i!==0 || out_q!==0)) $fatal(1,"Mute leaked output");
 if(out_valid) begin
  if(orr>=ow) $fatal(1,"Unexpected output");
  if({clipped,out_q,out_i} !== outputs[orr][32:0]) $fatal(1,"Output crossing mismatch %0d actual=%h expected=%h latest=%d count=%d/%d bank=%d active=%d",orr,{clipped,out_q,out_i},outputs[orr][32:0],dut.latest,ow,orr,dut.result[33],dut.active_table);
  orr=orr+1;
 end
end
always @(posedge core_clk) begin
 if(!dut.core_reset && dut.core_valid) begin
  if(ir>=iw || dut.core_input!==inputs[ir]) $fatal(1,"Input crossing mismatch %0d",ir);
  ir=ir+1;
 end
 if(!dut.core_reset && dut.core_output_valid && dut.core_table==dut.active_table && dut.running && !scene_muted) begin
  outputs[ow]={dut.core_table,dut.core_clipped,dut.core_q,dut.core_i};ow=ow+1;
 end
end
initial begin
 for(n=0;n<11500;n=n+1) begin
  @(negedge clk);
  reset=n<4;
  configure=n==12 || n==5000 || n==5050;restart=configure;
  if(configure) begin enabled=n==5000 ? 0 : 15;scene_muted=n==5000;end
  sample_valid=n>=8 && n<11200 && (($random(seed)&7)!=0);
  sample_i=$random(seed)&16'hfff0;sample_q=$random(seed)&16'hfff0;
 end
 @(negedge clk);
 if(ir!=iw || orr!=ow || orr<1000) $fatal(1,"Crossing counts %0d/%0d inputs %0d/%0d outputs",ir,iw,orr,ow);
 $display("PASS: %0d coherent input snapshots and %0d output frames across both clock domains",ir,orr);
 $finish;
end
endmodule
