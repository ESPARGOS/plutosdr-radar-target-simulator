// Four continuously resampled echoes. Delay motion and carrier Doppler share
// the same velocity, while each path has an independent amplitude and phase.
module target_bank
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
    reg preparing, prepared, active_table, settle, pending_restart;
    reg [N - 1 : 0] active_enabled;
    reg [12 : 0] prepare_count;
    wire [12 : 0] write_slot = prepare_count - 2'd2;
    wire [9 : 0] write_index = write_slot[11 : 2];
    wire [1 : 0] write_target = write_slot[1 : 0];
    reg activation_ready;
    wire activate = activation_ready && !configure;
    wire mute_now = configure && scene_muted;
    wire flush = activate || mute_now;
    wire [N - 1 : 0] motion_ready;
    assign reload_busy = preparing || settle || !(&motion_ready);
    wire [31 : 0] prepare_trig;
    reg [31 : 0] prepare_trig_pipe;
    reg signed [16 : 0] prepare_gain;
    reg signed [32 : 0] prepare_cosine, prepare_sine;
    nco_rom prepare_rom(.addr(prepare_count[11 : 2]),
                        .data(prepare_trig));
    always @(posedge clk) begin
        activation_ready <= preparing && prepare_count == 4097 && !configure && !reset;
        if (preparing && !configure) begin
            prepare_trig_pipe <= prepare_trig;
            prepare_gain <= $signed({1'b0, gains[prepare_count[1 : 0] * 16 +: 16]});
            prepare_cosine <= $signed(prepare_trig_pipe[15 : 0]) * prepare_gain;
            prepare_sine <= $signed(prepare_trig_pipe[31 : 16]) * prepare_gain;
        end
        if (reset) begin
            preparing <= 0;
            prepared <= 0;
            prepare_count <= 0;
            active_table <= 0;
            settle <= 0;
            active_enabled <= 0;
            pending_restart <= 0;
            sample_count <= 0;
        end else begin
            if (sample_valid)
                sample_count <= sample_count + 1'b1;
            if (configure) begin
                prepare_count <= 0;
                pending_restart <= restart;
                if (scene_muted) begin
                    preparing <= 0;
                    prepared <= 0;
                    settle <= 0;
                    active_enabled <= 0;
                end else
                    preparing <= 1;
            end else if (activate) begin
                preparing <= 0;
                prepared <= 0;
                settle <= 1;
                active_table <= ~active_table;
                active_enabled <= enabled;
            end else begin
                if (preparing)
                    prepare_count <= prepare_count + 1'b1;
                if (settle) begin
                    settle <= 0;
                    prepared <= 1;
                end
            end
        end
    end
    localparam SUM_W = 20 + $clog2(N);
    wire signed [19 : 0] rotated_i[0 : N - 1], rotated_q[0 : N - 1];
    wire [N - 1 : 0] interpolated_valid;
    wire [9:0] interpolation_fraction[0:N-1];
    wire [143:0] interpolation_coefficients[0:N-1];
    reg [5 : 0] valid_pipe;
    (* use_dsp = "no" *) reg signed [20 : 0] pair_i[0 : 1], pair_q[0 : 1];
    wire signed [SUM_W - 1 : 0] sum_i = $signed(pair_i[0]) + $signed(pair_i[1]);
    wire signed [SUM_W - 1 : 0] sum_q = $signed(pair_q[0]) + $signed(pair_q[1]);
    (* keep = "true" *) reg signed [SUM_W - 1 : 0] final_sum_i, final_sum_q;
    wire overflow_i = final_sum_i[SUM_W - 1 : 15] != {(SUM_W - 15){final_sum_i[15]}};
    wire overflow_q = final_sum_q[SUM_W - 1 : 15] != {(SUM_W - 15){final_sum_q[15]}};
    function automatic
        signed [15 : 0] saturate(input signed [SUM_W - 1 : 0] x);
        if (x[SUM_W - 1 : 15] == {(SUM_W - 15){x[15]}})
            saturate = x[15 : 0];
        else
            saturate = x[SUM_W - 1] ? 16'sh8000 : 16'sd32767;
    endfunction
    reg signed [15 : 0] output_i, output_q;
    reg output_overflow;
    assign out_i = output_i;
    assign out_q = output_q;
    assign out_valid = valid_pipe[5];
    always @(posedge clk) begin
        valid_pipe <= {valid_pipe[4 : 0], interpolated_valid[0]};
        final_sum_i <= sum_i;
        final_sum_q <= sum_q;
        for (integer p = 0; p < 2; p = p + 1) begin
            if (valid_pipe[2]) begin
                pair_i[p] <= $signed(rotated_i[2 * p]) + $signed(rotated_i[2 * p + 1]);
                pair_q[p] <= $signed(rotated_q[2 * p]) + $signed(rotated_q[2 * p + 1]);
            end
            if (reset || flush) begin
                pair_i[p] <= 0;
                pair_q[p] <= 0;
            end
        end
        if (valid_pipe[4]) begin
            output_i <= saturate(final_sum_i);
            output_q <= saturate(final_sum_q);
            output_overflow <= overflow_i || overflow_q;
        end
        if (out_valid && output_overflow)
            clipped <= 1;
        if (reset || flush) begin
            valid_pipe <= 0;
            clipped <= 0;
            output_i <= 0;
            output_q <= 0;
            output_overflow <= 0;
        end
    end
    generate
        for (genvar pair = 0; pair < N / 2; pair = pair + 1) begin : filter_tables
            fractional_rom rom(.clk(clk), .fast_profile(fast_profile),
                .address0(interpolation_fraction[2*pair]),
                .address1(interpolation_fraction[2*pair+1]),
                .coefficients0(interpolation_coefficients[2*pair]),
                .coefficients1(interpolation_coefficients[2*pair+1]));
        end
        for (genvar t = 0; t < N; t = t + 1) begin : target
            wire [AW - 1 : 0] position;
            wire [9 : 0] fraction;
            assign interpolation_fraction[t] = fraction;
            wire [31 : 0] phase, phase_step, next_phase;
            target_motion #(.AW(AW))
                motion(.clk(clk),
                       .reset(reset),
                       .configure(flush),
                       .sample_valid(sample_valid),
                       .moving(moving[t]),
                       .enabled(enabled[t]),
                       .edit_position(position_edits[t]),
                       .edit_velocity(velocity_edits[t]),
                       .restart_phase(activate ? pending_restart : restart),
                       .initial_integer(delays[t * AW +: AW]),
                       .initial_fraction(fractions[t * 16 +: 16]),
                       .upper_integer(upper),
                       .delay_step(delay_steps[t * 48 +: 48]),
                       .phase_step(increments[t * 32 +: 32]),
                       .delay_integer(position),
                       .delay_fraction(fraction),
                       .phase(phase),
                       .phase_next(next_phase),
                       .current_phase_step(phase_step),
                       .ready(motion_ready[t]),
                       .current_fraction(current_fractions[t * 16 +: 16]));
            assign current_delays[t * AW +: AW] = position;
            assign current_increments[t * 32 +: 32] = phase_step;
            wire signed [17 : 0] delayed_i, delayed_q;
            fractional_delay #(.AW(AW))
                delay_line(.clk(clk),
                           .reset(reset),
                           .flush(flush),
                           .produce(prepared && (&motion_ready)),
                           .sample_valid(sample_valid),
                           .sample_i(sample_i),
                           .sample_q(sample_q),
                           .delay_integer(position),
                           .coefficients(interpolation_coefficients[t]),
                           .output_valid(interpolated_valid[t]),
                           .output_i(delayed_i),
                           .output_q(delayed_q));
            (* ram_style = "block" *) reg [31 : 0] coefficients[0 : 2047];
            reg [31 : 0] trig, trig_pipe[0 : 11], trig1;
            (* keep = "true" *) reg [10 : 0] trig_address;
            // Two shared multipliers fill the inactive tables one target at a time.
            // The active scene continues until all four new tables are complete.
            always @(posedge clk) begin
                trig_address <= {active_table, next_phase[31 : 22]};
                trig <= coefficients[trig_address];
                trig_pipe[0] <= trig;
                for (integer p = 1; p < 12; p = p + 1)
                    trig_pipe[p] <= trig_pipe[p - 1];
                if (preparing && !configure) begin
                    if (prepare_count >= 2 && prepare_count <= 4097 && write_target == t)
                        coefficients[{~active_table, write_index}] <=
                            {prepare_sine[30 : 15], prepare_cosine[30 : 15]};
                end
            end
            reg signed [17 : 0] data_i, data_q;
            reg signed [18 : 0] data_sum;
            reg signed [16 : 0] trig_sum, trig_difference;
            reg signed [34 : 0] common_product, cross_i, cross_q;
            wire signed [35 : 0] product_i = $signed({common_product[34], common_product}) -
                                             $signed({cross_i[34], cross_i});
            wire signed [35 : 0] product_q = $signed({common_product[34], common_product}) +
                                             $signed({cross_q[34], cross_q});
            reg signed [19 : 0] rotation_i, rotation_q;
            assign rotated_i[t] = rotation_i;
            assign rotated_q[t] = rotation_q;
            always @(posedge clk) begin
                data_i <= active_enabled[t] ? delayed_i : 18'd0;
                data_q <= active_enabled[t] ? delayed_q : 18'd0;
                data_sum <= active_enabled[t] ? $signed(delayed_i) + $signed(delayed_q) : 19'sd0;
                trig1 <= trig_pipe[11];
                trig_sum <= $signed(trig_pipe[11][15 : 0]) + $signed(trig_pipe[11][31 : 16]);
                trig_difference <= $signed(trig_pipe[11][31 : 16]) - $signed(trig_pipe[11][15 : 0]);
                // Three real products implement an exact complex multiplication. All
                // intermediate bits are kept until the final Q1.15 scaling.
                rotation_i <= $signed(product_i) >>> 15;
                rotation_q <= $signed(product_q) >>> 15;
                common_product <= data_sum * $signed(trig1[15 : 0]);
                cross_i <= data_q * trig_sum;
                cross_q <= data_i * trig_difference;
            end
        end
    endgenerate
endmodule
