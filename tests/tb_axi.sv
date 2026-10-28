module tb_axi;
reg clean_locked=0;wire clean_enable,clean_run;
reg clk=0,rf=0;always #5 clk=~clk;always #8 rf=~rf;
reg rstn=0,sample_reset=1,adc_valid=1;
reg [11:0] awaddr=0,araddr=0;reg awvalid=0,wvalid=0,arvalid=0,bready=0,rready=0;
reg [31:0] wdata=0;reg [3:0] wstrb=15;
wire awready,wready,bvalid,arready,rvalid;wire [1:0] bresp,rresp;wire [31:0] rdata;wire [15:0] oi,oq;wire ov;
radar_axi dut(.clean_locked(clean_locked),.clean_enable(clean_enable),.clean_run(clean_run),.s_axi_aclk(clk),.s_axi_aresetn(rstn),.s_axi_awaddr(awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),.s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),.s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),.s_axi_araddr(araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),.s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),.sample_clk(rf),.sample_reset(sample_reset),.adc_valid(adc_valid),.adc_i(16'd1000),.adc_q(16'd0),.dac_i(oi),.dac_q(oq),.output_valid(ov));
task write_reg(input [11:0] a,input [31:0] d,input [3:0] st,input integer gap);
 begin
  // Exercise W before AW and AW before W independently.
  if(gap>=0)begin
   @(negedge clk);awaddr=a;awvalid=1;@(posedge clk);while(!awready)@(posedge clk);
   @(negedge clk);awvalid=0;repeat(gap)@(negedge clk);wdata=d;wstrb=st;wvalid=1;
   @(posedge clk);while(!wready)@(posedge clk);@(negedge clk);wvalid=0;
  end else begin
   @(negedge clk);wdata=d;wstrb=st;wvalid=1;@(posedge clk);while(!wready)@(posedge clk);
   @(negedge clk);wvalid=0;repeat(-gap)@(negedge clk);awaddr=a;awvalid=1;
   @(posedge clk);while(!awready)@(posedge clk);@(negedge clk);awvalid=0;
  end
  while(!bvalid)@(negedge clk);
  if(bresp!=0)$fatal(1,"AXI write failed %h",a);
  repeat(3)begin @(negedge clk);if(!bvalid)$fatal(1,"Lost write response under backpressure");end
  bready=1;@(negedge clk);bready=0;
 end
endtask
task read_reg(input [11:0] a,input [31:0] expected);
 begin
  @(negedge clk);araddr=a;arvalid=1;@(posedge clk);while(!arready)@(posedge clk);
  @(negedge clk);arvalid=0;while(!rvalid)@(negedge clk);
  if(rresp!=0 || rdata!==expected)$fatal(1,"Read %h: got %h expected %h",a,rdata,expected);
  repeat(3)begin @(negedge clk);if(!rvalid || rdata!==expected)$fatal(1,"Read backpressure");end
  rready=1;@(negedge clk);rready=0;
 end
endtask
initial begin
 #500000;$fatal(1,"AXI test timeout");
end
initial begin
 repeat(5)@(negedge clk);rstn=1;sample_reset=0;
 read_reg('h24,0);
 write_reg('h24,1,1,0);repeat(4)@(negedge clk);
 if(!clean_enable || !clean_run)$fatal(1,"MMCM did not start");
 clean_locked=1;repeat(4)@(negedge clk);read_reg('h24,7);
 write_reg('h24,0,1,0);
 if(clean_enable || !clean_run)$fatal(1,"MMCM stopped before mux switched");
 repeat(200)@(negedge clk);
 if(!clean_run)$fatal(1,"Clock shutdown grace period too short");
 repeat(60)@(negedge clk);
 if(clean_run)$fatal(1,"MMCM failed to stop");
 clean_locked=0;repeat(4)@(negedge clk);read_reg('h24,0);
 // Rapid disable/re-enable cancels shutdown without stopping the clock.
 write_reg('h24,1,1,0);repeat(4)@(negedge clk);
 write_reg('h24,0,1,0);repeat(50)@(negedge clk);
 write_reg('h24,1,1,0);repeat(300)@(negedge clk);
 if(!clean_run)$fatal(1,"Rapid re-enable stopped MMCM");
 read_reg(0,32'h52545331);read_reg(8,4);read_reg(12,2047);
 write_reg('h40,32'h12345678,15,2);write_reg('h40,32'h0000abcd,3,-4);read_reg('h40,32'h1234abcd);
 write_reg('h40,17,15,1);write_reg('h44,32'hfedcba98,15,-1);write_reg('h48,16384,15,0);write_reg('h20,1,15,0);
 if(dut.enabled!=0)$fatal(1,"Shadow write leaked into active config");
 write_reg('h10,1,15,0);repeat(10)@(negedge clk);
 if(dut.enabled!=1 || dut.delays[10:0]!=17 || dut.increments[31:0]!=32'hfedcba98 || dut.gains[15:0]!=16384)$fatal(1,"Atomic CDC commit failed");
 if(!dut.busy)$fatal(1,"Configuration acknowledged before tables were ready");
 repeat(1200)@(negedge rf);
 if(dut.busy)$fatal(1,"Configuration never acknowledged after table handoff");
 write_reg('h40,29,15,0);
 if(dut.delays[10:0]!=17)$fatal(1,"Configuration changed without commit");
 write_reg('h20,0,15,0);write_reg('h10,1,15,0);repeat(20)@(negedge clk);
 if(dut.enabled!=0 || oi!=0 || oq!=0)$fatal(1,"Mute did not silence output");
 $display("PASS: sequenced clock control; AXI split channels, byte strobes, backpressure, CDC atomic commit and mute");$finish;
end
endmodule
