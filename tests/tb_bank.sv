module tb;
reg clk=0;always #5 clk=~clk;
reg reset,configure,restart,valid;
reg signed [15:0] ii,qq;
reg [3:0] enabled;reg [43:0] delays;reg [127:0] inc;reg [63:0] gains;
wire signed [15:0] oi,oq;wire ov,clip;wire [31:0] count;
target_bank dut(.clk(clk),.reset(reset),.configure(configure),.restart(restart),
 .sample_valid(valid),.sample_i(ii),.sample_q(qq),.enabled(enabled),.delays(delays),
 .increments(inc),.gains(gains),.out_i(oi),.out_q(oq),.out_valid(ov),.clipped(clip),.sample_count(count));
integer f,o,n;integer r,c,s,v,i,q,m,d0,d1,d2,d3,g0,g1,g2,g3;
reg [31:0] f0,f1,f2,f3;
initial begin
 f=$fopen("stimulus.txt","r");o=$fopen("output.txt","w");
 while(!$feof(f))begin
  n=$fscanf(f,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",r,c,s,v,i,q,m,d0,d1,d2,d3,f0,f1,f2,f3,g0,g1,g2,g3);
  if(n==19)begin
   @(negedge clk);reset=r;configure=c;restart=s;valid=v;ii=i;qq=q;enabled=m;
   delays={d3[10:0],d2[10:0],d1[10:0],d0[10:0]};inc={f3,f2,f1,f0};gains={g3[15:0],g2[15:0],g1[15:0],g0[15:0]};
   @(posedge clk);#1;$fwrite(o,"%0d %0d %0d %0d\n",ov,oi,oq,clip);
  end
 end
 $fclose(o);$finish;
end
endmodule
