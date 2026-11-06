module tb;
reg clk=0;always #5 clk=~clk;
reg reset,configure,valid,moving,enabled,ep,ev,restart;
reg [13:0] initial_integer,upper;
reg [15:0] initial_fraction;
reg signed [47:0] step;
reg [31:0] inc;
wire [13:0] di;wire [9:0] df;wire [15:0] frac;wire [31:0] phase,current;
target_motion dut(.clk(clk),.reset(reset),.configure(configure),.sample_valid(valid),.moving(moving),
 .enabled(enabled),.edit_position(ep),.edit_velocity(ev),.restart_phase(restart),.initial_integer(initial_integer),
 .initial_fraction(initial_fraction),.upper_integer(upper),.delay_step(step),.phase_step(inc),
 .delay_integer(di),.delay_fraction(df),.phase(phase),.current_phase_step(current),.current_fraction(frac));
integer f,o,n,r,c,v,m,e,pd,vd,rp,d,fr,u;reg signed [63:0] st;reg[31:0] ph;
initial begin
 f=$fopen("motion-stimulus.txt","r");o=$fopen("motion-output.txt","w");
 while(!$feof(f)) begin
   n=$fscanf(f,"%d %d %d %d %d %d %d %d %d %d %d %d %d\n",r,c,v,m,e,pd,vd,rp,d,fr,u,st,ph);
   if(n==13) begin
     @(negedge clk);reset=r;configure=c;valid=v;moving=m;enabled=e;ep=pd;ev=vd;restart=rp;
     initial_integer=d;initial_fraction=fr;upper=u;step=st;inc=ph;
     @(posedge clk);#1;$fwrite(o,"%0d %0d %0d %0d %0d\n",di,df,frac,phase,current);
   end
 end
 $fclose(o);$finish;
end
endmodule
