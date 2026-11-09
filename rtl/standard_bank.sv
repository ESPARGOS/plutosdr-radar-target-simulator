// Four continuously resampled echoes. Delay motion and carrier Doppler share
// the same velocity, while each path has an independent amplitude and phase.
module standard_bank
    #(parameter N = 4,
      parameter AW = 14)
    (input wire clk, core_clk, core_locked, reset, configure, restart, sample_valid, fast_profile, scene_muted,
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
    assign reload_busy = preparing || settle || !(&motion_ready) || !core_locked;
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
    wire [N*14-1:0] position;
    wire [N*10-1:0] fraction, phase_address;
    for(genvar t=0;t<N;t=t+1) begin:motion_paths
        wire [31:0] phase,next_phase;
        target_motion #(.AW(AW)) motion(
            .clk(clk),.reset(reset),.configure(flush),.sample_valid(sample_valid),
            .moving(moving[t]),.enabled(enabled[t]),
            .edit_position(position_edits[t]),.edit_velocity(velocity_edits[t]),
            .restart_phase(activate ? pending_restart : restart),
            .initial_integer(delays[t*AW+:AW]),.initial_fraction(fractions[t*16+:16]),
            .upper_integer(upper),.delay_step(delay_steps[t*48+:48]),
            .phase_step(increments[t*32+:32]),.delay_integer(position[t*14+:14]),
            .delay_fraction(fraction[t*10+:10]),.phase(phase),.phase_next(next_phase),
            .current_phase_step(current_increments[t*32+:32]),.ready(motion_ready[t]),
            .current_fraction(current_fractions[t*16+:16]));
        assign current_delays[t*14+:14]=position[t*14+:14];
        assign phase_address[t*10+:10]=next_phase[31:22];
    end
    // Input samples and target state are captured together before the clock crossing.
    (* DONT_TOUCH="TRUE" *) reg [165:0] input_mailbox;
    reg input_toggle;
    wire running=prepared && (&motion_ready);
    always @(posedge clk) begin
        if(sample_valid) begin
            input_mailbox <= {scene_muted || !running, active_table,
                              running ? active_enabled : 4'd0,
                              phase_address,fraction,position,
                              sample_q[15:4],sample_i[15:4]};
            input_toggle<=~input_toggle;
        end
        if(reset) input_toggle<=0;
    end
    wire reset_request=reset || !core_locked;
    (* ASYNC_REG="TRUE" *) reg [1:0] reset_pipe=2'b11;
    always @(posedge core_clk or posedge reset_request)
        if(reset_request) reset_pipe<=2'b11;
        else reset_pipe<={reset_pipe[0],1'b0};
    wire core_reset=reset_pipe[1];
    (* ASYNC_REG="TRUE" *) reg input_meta,input_sync;
    reg input_seen,core_valid;
    reg [165:0] core_input;
    always @(posedge core_clk) begin
        input_meta<=input_toggle;input_sync<=input_meta;
        core_valid<=input_sync!=input_seen;
        if(input_sync!=input_seen) begin input_seen<=input_sync;core_input<=input_mailbox;end
        if(core_reset) begin input_meta<=0;input_sync<=0;input_seen<=0;core_valid<=0;end
    end
    wire [15:0] core_i,core_q;
    wire core_output_valid,core_table,core_clipped;
    standard_targets processing(
        .clk(core_clk),.reset(core_reset),.valid(core_valid),.sample(core_input[23:0]),
        .delays(core_input[79:24]),.fractions(core_input[119:80]),
        .phases(core_input[159:120]),.enabled(core_input[163:160]),
        .active_table(core_input[164]),.muted(core_input[165]),
        .table_clk(clk),.table_write(preparing && !configure && prepare_count>=2 && prepare_count<=4097),
        .table_address({~active_table,write_target,write_index}),
        .table_data({prepare_sine[30:15],prepare_cosine[30:15]}),
        .out_i(core_i),.out_q(core_q),.out_valid(core_output_valid),
        .out_table(core_table),.clipped(core_clipped));
    // Four result slots keep each frame stable while its Gray-coded pointer crosses.
    reg [33:0] results[0:3];
    reg [1:0] write_count,write_gray;
    wire [1:0] next_count=write_count+2'd1;
    always @(posedge core_clk) begin
        if(core_output_valid) begin
            results[write_count]<={core_table,core_clipped,core_q,core_i};
            write_count<=next_count;write_gray<=next_count^(next_count>>1);
        end
        if(core_reset) begin write_count<=0;write_gray<=0;end
    end
    (* ASYNC_REG="TRUE" *) reg [1:0] result_meta,result_sync;
    reg [1:0] result_seen;
    wire [1:0] completed={result_sync[1],result_sync[1]^result_sync[0]};
    wire [1:0] latest=completed-2'd1;
    wire [33:0] result=results[latest];
    reg [15:0] result_i,result_q;
    reg result_valid;
    assign out_i=result_i;
    assign out_q=result_q;
    assign out_valid=result_valid;
    always @(posedge clk) begin
        result_meta<=write_gray;result_sync<=result_meta;
        result_valid<=0;
        if(result_sync!=result_seen) begin
            result_seen<=result_sync;
            if(result[33]==active_table) begin
                result_i<=result[15:0];result_q<=result[31:16];clipped<=result[32];
                result_valid<=1;
            end
        end
        if(reset || flush || !running || scene_muted || !core_locked) begin
            result_i<=0;result_q<=0;result_valid<=0;clipped<=0;
        end
        if(reset) begin result_meta<=0;result_sync<=0;result_seen<=0;end
    end
endmodule
