// Sample-clock round-trip delay and carrier phase, with 48 fractional bits.
// delay_step = -f_D/f_carrier samples per input sample.
module target_motion
    #(parameter AW = 14)
    (input wire clk, reset, configure, sample_valid,
     input wire moving, enabled, edit_position, edit_velocity, restart_phase,
     input wire [AW - 1 : 0] initial_integer, upper_integer,
     input wire [15 : 0] initial_fraction,
     input wire signed [47 : 0] delay_step,
     input wire [31 : 0] phase_step,
     output wire [AW - 1 : 0] delay_integer,
     output wire [9 : 0] delay_fraction,
     output reg [31 : 0] phase,
     output wire [31 : 0] current_phase_step, phase_next,
     output wire [15 : 0] current_fraction,
     output wire ready);
    localparam W = AW + 49;
    // A DSP holds and advances the fractional position. The integer counter
    // uses the predicted carry/borrow, keeping it outside the feedback adder.
    reg [AW - 1 : 0] integer_state;
    (* use_dsp = "yes" *) reg [47 : 0] fraction_state;
    wire [W - 1 : 0] position = {1'b0, integer_state, fraction_state};
    reg [47 : 0] active_step, opposite_step, reflection_threshold;
    reg [31 : 0] active_phase_step, opposite_phase_step;
    reg forward, active, motion_enabled, wrapped;
    // Keep the two boundary decisions separate so neither direction passes
    // through a wide comparison followed by a direction multiplexer.
    (* DONT_TOUCH = "TRUE" *) reg crossing_upper, crossing_lower;
    wire crossing = crossing_upper || crossing_lower;
    reg [AW - 1 : 0] upper, upper_previous;
    reg [47 : 0] threshold_positive, threshold_negative;
    reg [1 : 0] configuration_stage;

    // Manual edits pass through a short control pipeline. Samples are withheld
    // during this handoff; ordinary motion never enters this pipeline.
    reg [W - 1 : 0] candidate_position, configured_position;
    reg [47 : 0] candidate_step, configured_step, configured_opposite_step;
    reg [31 : 0] candidate_phase, configured_phase_step, configured_opposite_phase_step;
    // The same window reaches all targets, but each comparator needs a local copy.
    (* DONT_TOUCH = "TRUE" *) reg [AW - 1 : 0] configured_upper;
    reg configured_enabled, configured_moving, configured_restart, configured_direction,
        configured_clamp;
    wire [47 : 0] inverse_candidate = -candidate_step;
    wire clamp_candidate =
             candidate_position[48 +: AW] > configured_upper ||
             (candidate_position[48 +: AW] == configured_upper && candidate_position[47 : 0] != 0);

    wire [AW - 1 : 0] integer_position = position[48 +: AW];
    wire [47 : 0] fraction = position[47 : 0];
    (* keep = "true" *) wire [2 : 0] less, greater, equal_low, equal_high;
    for (genvar part = 0; part < 3; part = part + 1) begin : compare_fraction
        assign less[part] = fraction[16 * part +: 16] < threshold_positive[16 * part +: 16];
        assign greater[part] = fraction[16 * part +: 16] > threshold_negative[16 * part +: 16];
        // Three-bit equality fits one LUT. Keep these groups separate so
        // equality does not share the slower magnitude-comparison carry chain.
        (* dont_touch = "true" *) wire [5:0] equal_positive, equal_negative;
        for (genvar group = 0; group < 5; group = group + 1) begin : equal_group
            assign equal_positive[group] = fraction[16*part + 3*group +: 3] ==
                                           threshold_positive[16*part + 3*group +: 3];
            assign equal_negative[group] = fraction[16*part + 3*group +: 3] ==
                                           threshold_negative[16*part + 3*group +: 3];
        end
        assign equal_positive[5] = fraction[16*part + 15] == threshold_positive[16*part + 15];
        assign equal_negative[5] = fraction[16*part + 15] == threshold_negative[16*part + 15];
        assign equal_low[part] = &equal_positive;
        assign equal_high[part] = &equal_negative;
    end
    wire below_fraction = less[2] || (equal_low[2] && (less[1] || (equal_low[1] && less[0])));
    wire above_fraction =
             greater[2] || (equal_high[2] && (greater[1] || (equal_high[1] && greater[0])));
    wire upper_ahead = forward && active_step != 0 &&
                       (integer_position == upper ||
                        (integer_position == upper_previous && above_fraction));
    wire lower_ahead = !forward && integer_position == 0 && below_fraction;
    // Predict fractional carry/borrow along with the range-boundary crossing.
    // Since |step| < 1/2, two consecutive steps cannot both wrap the fraction.
    // This keeps the integer counter out of the wide fractional adder's path.
    wire fraction_wrap_ahead =
             forward ? active_step != 0 && (above_fraction || (&equal_high)) : below_fraction;
    wire [AW - 1 : 0] next_integer =
                          forward ? integer_position + wrapped : integer_position - wrapped;
    (* use_dsp = "yes" *) reg [47 : 0] reflected_fraction;
    // Seed one sample ahead, then predict two samples ahead. The prediction
    // immediately after a reflection is unused: |step| < 1/2 and upper >= 1.
    always @(posedge clk) begin
        // Paused trajectories do not consume this prediction. Configuration
        // reseeds it before motion resumes, so their enables need not fan out
        // through the DSP's clock-enable logic.
        if (sample_valid || configuration_stage == 3)
            reflected_fraction <= reflection_threshold - fraction;
    end
    // Loading and reflection select the adder operands. Normal motion uses
    // its own registered output as feedback, with no fabric carry chain.
    wire loading_position = configuration_stage == 2;
    wire advancing_position = configuration_stage == 0 && sample_valid && active && motion_enabled;
    always @(posedge clk) begin
        if (reset)
            fraction_state <= 0;
        else if (!configure) begin
            if (loading_position)
                fraction_state <= configured_clamp ? 48'd0 : configured_position[47:0];
            else if (advancing_position) begin
                if (crossing)
                    fraction_state <= reflected_fraction;
                else
                    fraction_state <= fraction_state + active_step;
            end
        end
    end
    assign current_phase_step = active_phase_step;
    assign phase_next = !sample_valid || !ready ? phase : phase + active_phase_step;
    assign delay_integer = integer_position;
    assign delay_fraction = fraction[47 : 38];
    assign current_fraction = fraction[47 : 32];
    assign ready = configuration_stage == 0 && !configure;

    always @(posedge clk) begin
        if (reset) begin
            integer_state <= 0;
            active_step <= 0;
            opposite_step <= 0;
            reflection_threshold <= 0;
            phase <= 0;
            active_phase_step <= 0;
            opposite_phase_step <= 0;
            forward <= 1;
            active <= 0;
            motion_enabled <= 0;
            crossing_upper <= 0;
            crossing_lower <= 0;
            wrapped <= 0;
            upper <= 0;
            upper_previous <= 0;
            threshold_positive <= 0;
            threshold_negative <= 0;
            configuration_stage <= 0;
        end else if (configure) begin
            candidate_position <= edit_position || !motion_enabled
                                      ? {1'b0, initial_integer, initial_fraction, 32'd0}
                                      : position;
            candidate_step <= edit_velocity || !motion_enabled ? delay_step : active_step;
            candidate_phase <= edit_velocity || !motion_enabled ? phase_step : current_phase_step;
            configured_upper <= upper_integer;
            configured_enabled <= enabled;
            configured_moving <= moving;
            configured_restart <= restart_phase;
            configuration_stage <= 1;
        end else if (configuration_stage == 1) begin
            configured_position <= candidate_position;
            configured_clamp <= configured_moving && clamp_candidate;
            configured_step <= candidate_step;
            configured_opposite_step <= inverse_candidate;
            configured_phase_step <= candidate_phase;
            configured_opposite_phase_step <= -candidate_phase;
            configured_direction <= !candidate_step[47];
            configuration_stage <= 2;
        end else if (configuration_stage == 2) begin
            integer_state <= configured_clamp ? configured_upper : configured_position[48 +: AW];
            active_step <= configured_step;
            opposite_step <= configured_opposite_step;
            active_phase_step <= configured_phase_step;
            opposite_phase_step <= configured_opposite_phase_step;
            reflection_threshold <= configured_opposite_step;
            forward <= configured_direction;
            active <= configured_enabled;
            motion_enabled <= configured_moving;
            upper <= configured_upper;
            upper_previous <= configured_upper - 1'b1;
            threshold_positive <= configured_direction ? configured_step : configured_opposite_step;
            threshold_negative <= configured_direction ? configured_opposite_step : configured_step;
            if (configured_restart)
                phase <= 0;
            configuration_stage <= 3;
        end else if (configuration_stage == 3) begin
            // Seed the first crossing decision using one step. Thereafter,
            // compare two steps ahead while the current sample is advanced.
            crossing_upper <= upper_ahead;
            crossing_lower <= lower_ahead;
            wrapped <= fraction_wrap_ahead;
            threshold_positive <= threshold_positive << 1;
            threshold_negative <= threshold_negative << 1;
            reflection_threshold <= opposite_step << 1;
            configuration_stage <= 0;
        end else if (sample_valid) begin
            // This branch already excludes configuration and invalid samples.
            // Keep the readiness mux out of the phase accumulator feedback.
            phase <= phase + active_phase_step;
            if (active && motion_enabled) begin
                if (crossing) begin
                    integer_state <= forward ? upper_previous : 0;
                    forward <= !forward;
                    active_step <= opposite_step;
                    opposite_step <= active_step;
                    active_phase_step <= opposite_phase_step;
                    opposite_phase_step <= active_phase_step;
                    reflection_threshold <= active_step << 1;
                end else
                    integer_state <= next_integer;
                // |step| < 1/2 and upper >= 1 guarantee that a reflected
                // target cannot cross the opposite boundary on the next sample.
                crossing_upper <= !crossing && upper_ahead;
                crossing_lower <= !crossing && lower_ahead;
                wrapped <= !crossing && !wrapped && fraction_wrap_ahead;
            end
        end
    end
endmodule
