// AXI-Lite registers at 0x43c00000; bundled-data toggle handshake to RF clock.
module radar_axi (
 input wire s_axi_aclk, s_axi_aresetn,
 input wire [11:0] s_axi_awaddr, input wire [2:0] s_axi_awprot,
 input wire s_axi_awvalid, output wire s_axi_awready,
 input wire [31:0] s_axi_wdata, input wire [3:0] s_axi_wstrb,
 input wire s_axi_wvalid, output wire s_axi_wready,
 output reg [1:0] s_axi_bresp, output reg s_axi_bvalid, input wire s_axi_bready,
 input wire [11:0] s_axi_araddr, input wire [2:0] s_axi_arprot,
 input wire s_axi_arvalid, output wire s_axi_arready,
 output reg [31:0] s_axi_rdata, output reg [1:0] s_axi_rresp,
 output reg s_axi_rvalid, input wire s_axi_rready,
 input wire sample_clk, sample_reset, adc_valid,
 input wire [15:0] adc_i,adc_q,
 output wire [15:0] dac_i,dac_q,
 input wire clean_locked,
 output reg clean_enable,
 output reg clean_run,
 output wire output_valid
);
 // Asynchronous assertion, synchronous release into the RF clock domain.
 (* ASYNC_REG="TRUE" *) reg [1:0] rf_reset_pipe = 2'b11;
 always @(posedge sample_clk or negedge s_axi_aresetn)
   if(!s_axi_aresetn) rf_reset_pipe<=2'b11;
   else rf_reset_pipe<={rf_reset_pipe[0],1'b0};
 wire rf_reset=rf_reset_pipe[1];
 reg aw_pending,w_pending;
 reg [11:0] addr;
 reg [31:0] data;
 reg [3:0] strobes;
 reg [31:0] shadow [0:16];
 reg [543:0] mailbox;
 reg request, restart_mailbox;
 reg ack;
 (* ASYNC_REG="TRUE" *) reg ack_meta,ack_sync;
 (* ASYNC_REG="TRUE" *) reg req_meta,req_sync;
 (* ASYNC_REG="TRUE" *) reg clip_meta,clip_sync;
 reg [3:0] enabled;
 reg [43:0] delays;
 reg [127:0] increments;
 // Keep the bundled-data CDC capture flops explicit. Absorbing them into DSP
 // input registers changes the endpoint names used by radar_cdc.xdc.
 (* DONT_TOUCH="TRUE" *) reg [63:0] gains;
 (* ASYNC_REG="TRUE" *) reg clean_lock_meta,clean_lock_sync;
 reg configure,restart,cfg_pending;
 wire bank_reload_busy;
 // Keep the outgoing MMCM clock alive while BUFGCTRL switches to raw.
 // 256 AXI cycles (2.56 us) exceed three RF cycles throughout 75..150 MHz.
 reg [7:0] clean_stop_count;
 wire clipped;
 wire [31:0] sample_count;
 wire busy=request!=ack_sync;
 assign s_axi_awready=!aw_pending && !s_axi_bvalid;
 assign s_axi_wready=!w_pending && !s_axi_bvalid;
 assign s_axi_arready=!s_axi_rvalid;
 function automatic [31:0] merge(input [31:0] old, input [31:0] value,input [3:0] mask);
   for(integer b=0;b<4;b=b+1) merge[b*8+:8]=mask[b]?value[b*8+:8]:old[b*8+:8];
 endfunction
 integer i;
 always @(posedge s_axi_aclk) begin
   if(!s_axi_aresetn) begin
     clean_enable<=0;clean_run<=0;clean_stop_count<=0;clean_lock_meta<=0;clean_lock_sync<=0;
     aw_pending<=0;w_pending<=0;s_axi_bvalid<=0;s_axi_rvalid<=0;
     s_axi_bresp<=0;s_axi_rresp<=0;s_axi_rdata<=0;
     addr<=0;data<=0;strobes<=0;mailbox<=0;request<=0;restart_mailbox<=0;
     ack_meta<=0;ack_sync<=0;clip_meta<=0;clip_sync<=0;
     for(i=0;i<17;i=i+1) shadow[i]<=0;
   end else begin
     clean_lock_meta<=clean_locked;clean_lock_sync<=clean_lock_meta;
     if(clean_enable) begin clean_run<=1;clean_stop_count<=255;end
     else if(clean_stop_count!=0) clean_stop_count<=clean_stop_count-1;
     else clean_run<=0;
     ack_meta<=ack;ack_sync<=ack_meta;clip_meta<=clipped;clip_sync<=clip_meta;
     if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
     if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
     if(s_axi_awready && s_axi_awvalid) begin addr<=s_axi_awaddr;aw_pending<=1;end
     if(s_axi_wready && s_axi_wvalid) begin data<=s_axi_wdata;strobes<=s_axi_wstrb;w_pending<=1;end
     if(aw_pending && w_pending && !s_axi_bvalid) begin
       aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
       if(addr[1:0]!=0) s_axi_bresp<=2;
       else if(addr==12'h024 && strobes[0]) clean_enable<=data[0];
       else if(addr==12'h020) shadow[0]<=merge(shadow[0],data,strobes);
       else if(addr>=12'h040 && addr<12'h080) shadow[1+((addr-12'h040)>>2)]<=merge(shadow[1+((addr-12'h040)>>2)],data,strobes);
       else if(addr==12'h010 && strobes[0] && data[0]) begin
         if(busy) s_axi_bresp<=2;
         else begin
           for(i=0;i<17;i=i+1) mailbox[i*32+:32]<=shadow[i];
           restart_mailbox<=data[1];request<=~request;
         end
       end else s_axi_bresp<=2;
     end
     if(s_axi_arready && s_axi_arvalid) begin
       s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=0;
       case(s_axi_araddr)
         12'h000:s_axi_rdata<=32'h52545331; // RTS1
         12'h004:s_axi_rdata<=32'h00010006;
         12'h008:s_axi_rdata<=4;
         12'h00c:s_axi_rdata<=2047;
         12'h014:s_axi_rdata<={30'd0,ack_sync,busy};
         12'h018:s_axi_rdata<={31'd0,clip_sync};
         12'h020:s_axi_rdata<=shadow[0];
         12'h024:s_axi_rdata<={29'd0,clean_run,clean_lock_sync,clean_enable};
         default: if(s_axi_araddr>=12'h040 && s_axi_araddr<12'h080 && s_axi_araddr[1:0]==0)
           s_axi_rdata<=shadow[1+((s_axi_araddr-12'h040)>>2)];
         else s_axi_rresp<=2;
       endcase
     end
   end
 end
 // Mailbox is held stable until acknowledgment. Two synchronizer stages plus
 // one capture edge give bundled data time to settle. See radar_cdc.xdc.
 integer t;
 always @(posedge sample_clk) begin
   if(rf_reset) begin
     req_meta<=0;req_sync<=0;ack<=0;enabled<=0;delays<=0;
     increments<=0;gains<=0;configure<=0;restart<=0;cfg_pending<=0;
   end else begin
     req_meta<=request;req_sync<=req_meta;configure<=0;
     if(req_sync!=ack && !cfg_pending) begin
       enabled<=mailbox[3:0];restart<=restart_mailbox;
       for(t=0;t<4;t=t+1) begin
         delays[t*11+:11]<=mailbox[(1+4*t)*32+:11];
         increments[t*32+:32]<=mailbox[(2+4*t)*32+:32];
         gains[t*16+:16]<=mailbox[(3+4*t)*32+:16];
       end
       configure<=1;cfg_pending<=1;
     end else if(cfg_pending && !configure && !bank_reload_busy) begin
       ack<=req_sync;cfg_pending<=0;
     end
   end
 end
 target_bank bank(.clk(sample_clk),.reset(sample_reset || rf_reset),
   .configure(configure),.restart(restart),.sample_valid(adc_valid),
   .sample_i({adc_i[11:0],4'b0}),.sample_q({adc_q[11:0],4'b0}),.enabled(enabled),.delays(delays),
   .increments(increments),.gains(gains),.out_i(dac_i),.out_q(dac_q),
   .out_valid(output_valid),.clipped(clipped),.sample_count(sample_count),.reload_busy(bank_reload_busy));
endmodule
