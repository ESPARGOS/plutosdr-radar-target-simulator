module tb;
reg clk=0;always #5 clk=~clk;
reg reset,valid,fast;
reg signed [15:0] ii,qq;
reg [13:0] delay_integer;
reg [9:0] delay_fraction;
wire ov;wire signed [17:0] oi,oq;
wire [143:0] coefficients, coefficients_peer;
fractional_rom rom(.clk(clk),.fast_profile(fast),.address0(delay_fraction),.address1(delay_fraction),.coefficients0(coefficients),.coefficients1(coefficients_peer));
fractional_delay dut(.clk(clk),.reset(reset),.sample_valid(valid),.flush(1'b0),.produce(1'b1),.sample_i(ii),.sample_q(qq),
 .delay_integer(delay_integer),.coefficients(coefficients),.output_valid(ov),.output_i(oi),.output_q(oq));
integer f,o,n,r,v,i,q,d,frac,profile;
initial begin
 f=$fopen("fractional-stimulus.txt","r");o=$fopen("fractional-output.txt","w");
 while(!$feof(f)) begin
   n=$fscanf(f,"%d %d %d %d %d %d %d\n",r,v,i,q,d,frac,profile);
   if(n==7) begin
     @(negedge clk);reset=r;valid=v;fast=profile;ii=i;qq=q;delay_integer=d;delay_fraction=frac;
     @(posedge clk);#1;
     if (coefficients !== coefficients_peer)
       $fatal(1,"Coefficient ROM ports disagree for the same address");
     $fwrite(o,"%0d %0d %0d\n",ov,oi,oq);
   end
 end
 $fclose(o);$finish;
end
endmodule
