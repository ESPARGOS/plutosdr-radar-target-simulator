// Four continuously resampled echoes. Delay motion and carrier Doppler share
// the same velocity, while each path has an independent amplitude and phase.
module standard_clock
    #(parameter N = 4,
      parameter AW = 14)
    (input wire clk, reset, configure, restart, sample_valid, fast_profile, scene_muted,
     input wire signed [15 : 0] sample_i, sample_q,
     input wire [N - 1 : 0] enabled, moving, position_edits, velocity_edits,
     input wire [N * AW - 1 : 0] delays,
     input wire [N * 16 - 1 : 0] fractions, gains,
     input wire [N * 32 - 1 : 0] increments,
     input wire [N * 48 - 1 : 0] delay_steps,
     input wire [AW - 1 : 0] upper,
     output wire signed [15 : 0] out_i, out_q,
     output wire out_valid,
     output reg clipped,
     output wire reload_busy,
     output reg [31 : 0] sample_count,
     output wire [N * AW - 1 : 0] current_delays,
     output wire [N * 16 - 1 : 0] current_fractions,
     output wire [N * 32 - 1 : 0] current_increments);
    wire core_clk,core_locked,feedback,feedback_buffer,core_unbuffered;
    MMCME2_BASE #(.CLKIN1_PERIOD(16.276042),.CLKFBOUT_MULT_F(16.0),
                  .CLKOUT0_DIVIDE_F(4.0),.DIVCLK_DIVIDE(1)) clocks(
        .CLKIN1(clk),.RST(reset),.PWRDWN(1'b0),.CLKFBIN(feedback_buffer),
        .CLKFBOUT(feedback),.CLKOUT0(core_unbuffered),.LOCKED(core_locked));
    BUFG feedback_clock(.I(feedback),.O(feedback_buffer));
    BUFG processing_clock(.I(core_unbuffered),.O(core_clk));
    standard_bank #(.N(N),.AW(AW)) bank(.*);
endmodule
