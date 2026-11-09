module standard_history(input wire clk, write_enable,
 input wire [14:0] write_address, read_address,
 input wire [31:0] write_data,
 input wire [7:0] available,
 output reg [255:0] samples);
wire [31:0] values[0:7];
reg [2:0] bank0, bank1, bank2;
reg [7:0] bypass0,bypass1,bypass2,available0,available1,available2;
reg [31:0] new0,new1,new2;
always @(posedge clk) begin
 bank0<=read_address[2:0]; bank1<=bank0;bank2<=bank1;
 new0<=write_data;new1<=new0;new2<=new1;
 for(integer k=0;k<8;k=k+1) bypass0[k]<=write_enable && ((read_address-k)&32767)==write_address;
 bypass1<=bypass0; available0<=available;available1<=available0;available2<=available1;bypass2<=bypass1;
end
for(genvar b=0;b<8;b=b+1) begin:banks
 (* ram_style="block" *) reg [31:0] memory[0:4095];
 reg [31:0] data, data_pipe, write_word;
 reg [11:0] read_row, write_row;
 reg store;
 wire [11:0] row = read_address[14:3] - (read_address[2:0]<b);
 always @(posedge clk) begin
  read_row<=row;write_row<=write_address[14:3];write_word<=write_data;
  store<=write_enable && write_address[2:0]==b;
  if(store) memory[write_row]<=write_word;
  data<=memory[read_row];data_pipe<=data;
 end
 assign values[b]=data_pipe;
end
for(genvar k=0;k<8;k=k+1) begin:taps
 wire [2:0] bank=bank2-k;
 always @(posedge clk) samples[32*k+:32]<=!available2[k] ? 32'd0 : bypass2[k] ? new2 : values[bank];
end
endmodule
