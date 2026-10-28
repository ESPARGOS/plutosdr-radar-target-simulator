// Exercise the patched ADI logic. I/O primitives and AXI control are omitted;
// force their boundary signals, then compare old/new pipeline timing and IQ.
`timescale 1ns/100ps
module tb_interface;
 reg clk=0;
 always #5 clk=~clk;
 reg [15:0] dma=0;
 reg [3:0] sel=2;
 reg [11:0] iq_i=0,iq_q=0;
 wire [11:0] fast_tx,slow_tx;
 axi_ad9361_tx_channel #(.RADAR_LOW_LATENCY(1),.IQCORRECTION_DISABLE(1)) fast(
   .dac_clk(clk),.dac_valid(1'b1),.dac_data(fast_tx),.dma_data(dma),.adc_data(iq_i));
 axi_ad9361_tx_channel #(.IQCORRECTION_DISABLE(1)) slow(
   .dac_clk(clk),.dac_valid(1'b1),.dac_data(slow_tx),.dma_data(dma));
 wire [15:0] adc_stimulus={4'b0,iq_i};
 wire [15:0] fast_adc;
 wire fast_adc_valid;
 axi_ad9361 #(.RADAR_LOW_LATENCY(1),.TDD_DISABLE(1)) adc_gate(
   .clk(clk),.adc_data_i0(fast_adc),.adc_valid_i0(fast_adc_valid));
 reg [47:0] tx=0;
 wire [47:0] fast_rx,slow_rx;
 wire fast_valid,slow_valid;
 axi_ad9361_cmos_if #(.RADAR_LOW_LATENCY(1)) fi(
   .clk(clk),.adc_r1_mode(1'b1),.dac_r1_mode(1'b1),.dac_valid(1'b1),
   .dac_clksel(1'b0),.dac_data(tx),.adc_data(fast_rx),.adc_valid(fast_valid));
 axi_ad9361_cmos_if si(
   .clk(clk),.adc_r1_mode(1'b1),.dac_r1_mode(1'b1),.dac_valid(1'b1),
   .dac_clksel(1'b0),.dac_data(tx),.adc_data(slow_rx),.adc_valid(slow_valid));
 reg [11:0] previous_dma;
 reg [47:0] previous_rx;
 reg previous_valid;
 reg [25:0] previous_tx;
 integer n;
 initial begin
   force fast.dac_data_sel_s=sel; force slow.dac_data_sel_s=sel;
   force fast.dac_pn_data=12'habc; force slow.dac_pn_data=12'habc;
   force adc_gate.adc_data_i0_s=adc_stimulus;
   force adc_gate.adc_valid_i0_s=1'b1;
   force adc_gate.dac_data_s=tx;
   force fi.l_clk=clk; force si.l_clk=clk;
   force fi.rx_frame_s=2'b01; force si.rx_frame_s=2'b01;
   force fi.rx_data_0_s=iq_i; force si.rx_data_0_s=iq_i;
   force fi.rx_data_1_s=iq_q; force si.rx_data_1_s=iq_q;
   for(n=0;n<1000;n=n+1) begin
     @(negedge clk);
     previous_dma=dma[15:4];
     previous_rx=fast_rx;previous_valid=fast_valid;
     previous_tx={fi.tx_frame,fi.tx_data_1,fi.tx_data_0};
     dma=$random;iq_i=$random;iq_q=$random;tx={$random,$random};
     #1;
     if(fast_tx!==dma[15:4]) $fatal(1,"DMA bypass changed sample");
     if(fast_adc!=={4'b0,iq_i} || fast_adc_valid!==1'b1) $fatal(1,"ADC FDD bypass changed sample");
     @(posedge clk);#1;
     if(adc_gate.radar_loopback_data!==tx) $fatal(1,"Diagnostic loopback register changed data");
     if(n>3) begin
       if(slow_tx!==previous_dma) $fatal(1,"TX latency mismatch");
       if(slow_rx!==previous_rx || slow_valid!==previous_valid) $fatal(1,"RX transfer mismatch");
       if({si.tx_frame,si.tx_data_1,si.tx_data_0}!==previous_tx) $fatal(1,"TX transfer mismatch");
       if(fast_rx!=={24'b0,iq_q,iq_i}) $fatal(1,"IQ order changed");
     end
   end
   @(negedge clk);sel=9;
   repeat(4) @(posedge clk);
   #1;if(fast_tx!==12'habc || fast_tx!==slow_tx) $fatal(1,"PN calibration path changed");
   @(negedge clk);sel=3;
   repeat(4) @(posedge clk);
   #1;if(fast_tx!==0 || fast_tx!==slow_tx) $fatal(1,"Zero source changed");
   @(negedge clk);sel=10;
   repeat(10) begin
     iq_i=$random;#1;
     if(fast_tx!==iq_i) $fatal(1,"Diagnostic direct RX bypass changed sample");
   end
   $display("PASS: 1000 interface samples; IQ order, five bypass registers, PN and zero paths");
   $finish;
 end
endmodule
