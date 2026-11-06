// Pack three native 12-bit complex ADC samples into each 72-bit word.
// Four interleaved triplet banks supply up to eight interpolation taps.
module fractional_delay
    #(parameter AW = 14)
    (input wire clk, reset, sample_valid, flush, produce,
     input wire signed [15 : 0] sample_i, sample_q,
     input wire [AW - 1 : 0] delay_integer,
     input wire [143 : 0] coefficients,
     output reg output_valid,
     output reg signed [17 : 0] output_i, output_q);
    localparam DEPTH = 3 * (1 << (AW - 2));
    reg [AW - 1 : 0] write_pointer;
    reg [AW - 3 : 0] write_group;
    reg [1 : 0] write_lane;
    reg [AW : 0] filled;
    // All taps share the distance to the oldest available sample. Comparing
    // its low bits avoids a separate address-width adder for every tap.
    reg signed [AW : 0] history_distance;
    wire history_full = |history_distance[AW-1:3];
    wire bypass_near = !(|delay_integer[AW-1:2]);
    wire signed [3:0] bypass_distance = $signed({2'b0, write_lane}) -
                                         $signed({2'b0, delay_integer[1:0]});
    reg [71 : 0] partial;
    reg store_pending;
    reg [AW - 3 : 0] store_group;
    wire[23 : 0] sample = {sample_q[15 : 4], sample_i[15 : 4]};
    wire [71 : 0] current_word = write_lane == 0   ? {48'd0, sample}
                                 : write_lane == 1 ? {24'd0, sample, partial[23 : 0]}
                                                   : {sample, partial[47 : 0]};
    reg signed [AW : 0] difference;
    reg [AW - 1 : 0] normalized, normalized_pipe[0 : 1];
    (* rom_style = "distributed" *) reg [20:0] address_products[0:127];
    initial for (integer n = 0; n < 128; n = n + 1)
        address_products[n] = n * 10923;
    reg [20:0] address_low, address_high;
    reg [27:0] divided;
    wire [AW - 3 : 0] first_group = divided[AW + 12 : 15];
    (* shreg_extract = "no" *) reg [1 : 0] first_bank[0 : 1], first_lane[0 : 1];
    (* shreg_extract = "no" *) reg [71 : 0] bypass_word[0 : 5];
    (* shreg_extract = "no" *) reg [1 : 0] bypass_lane[0 : 5];
    (* shreg_extract = "no" *) reg [7 : 0] bypass[0 : 5];
    (* shreg_extract = "no" *) reg [7 : 0] available[1 : 5];
    reg [11 : 0] valid_pipe;
    wire [71 : 0] bank_data[0 : 3];
    // Keep the tap registers in logic so the memory-selection mux can be
    // placed independently of the fixed DSP columns. This adds no latency.
    (* dont_touch = "true" *) reg signed [15 : 0] tap_i[0 : 7], tap_q[0 : 7];
    reg signed [17 : 0] coefficient[0 : 7];
    wire signed [33 : 0] product_i[0 : 7], product_q[0 : 7];
    (* use_dsp = "no" *) reg signed [34 : 0] pair_i[0 : 3], pair_q[0 : 3];
    (* use_dsp = "no" *) reg signed [35 : 0] half_i[0 : 1], half_q[0 : 1];
    (* use_dsp = "no" *) reg signed [36 : 0] sum_i, sum_q;
    generate
        for (genvar b = 0; b < 4; b = b + 1) begin : banks
            (* ram_style = "block" *) reg [71 : 0] memory[0 : (DEPTH / 12) - 1];
            reg [71 : 0] read_data, read_pipe;
            wire [AW - 5 : 0] row_address = first_group[AW - 3 : 2] - (first_group[1 : 0] < b);
            always @(posedge clk) begin
                // The address pipeline reaches RAM after this registered write.
                // The front-word bypass supplies samples not yet stored here.
                if (store_pending && !reset && store_group[1 : 0] == b)
                    memory[store_group[AW - 3 : 2]] <= partial;
                if (valid_pipe[3])
                    read_data <= memory[row_address];
                read_pipe <= read_data;
            end
            assign bank_data[b] = read_pipe;
        end
        for (genvar k = 0; k < 8; k = k + 1) begin : taps
            wire [23 : 0] from_bank[0 : 2];
            for (genvar lane = 0; lane < 3; lane = lane + 1) begin : lanes
                localparam BACK = (k + 2 - lane) / 3;
                localparam SLOT = (lane + 9 - k) % 3;
                assign from_bank[lane] = bank_data[(first_bank[1] - BACK) & 3][24 * SLOT +: 24];
            end
            wire [1 : 0] recent_lane = bypass_lane[5] - k;
            wire [23 : 0] value = !available[5][k] ? 24'd0
                                  : bypass[5][k]   ? bypass_word[5][24 * recent_lane +: 24]
                                                   : from_bank[first_lane[1]];
            always @(posedge clk) begin
                tap_i[k] <= {value[11 : 0], 4'd0};
                tap_q[k] <= {value[23 : 12], 4'd0};
            end
        end
        for (genvar k = 0; k < 8; k = k + 1) begin : products
            if (k < 7) begin
                (* use_dsp = "yes" *) reg signed [33:0] pi, pq;
                always @(posedge clk) begin
                    pi <= tap_i[k] * coefficient[k];
                    pq <= tap_q[k] * coefficient[k];
                end
                reg signed [33:0] delayed_i, delayed_q;
                always @(posedge clk) begin
                    delayed_i <= pi; delayed_q <= pq;
                end
                assign product_i[k] = delayed_i;
                assign product_q[k] = delayed_q;
            end else begin
                // The last coefficient fits ten signed bits. Three small partial
                // products and their registered sum use logic rather than DSPs.
                localparam CW = 10;
                localparam SPLIT = 3;
                wire signed [11:0] vi = tap_i[k][15:4], vq = tap_q[k][15:4];
                wire signed [SPLIT:0] low = {1'b0, coefficient[k][SPLIT-1:0]};
                wire signed [SPLIT:0] middle = {1'b0, coefficient[k][2*SPLIT-1:SPLIT]};
                wire signed [CW-2*SPLIT-1:0] high = coefficient[k][CW-1:2*SPLIT];
                (* use_dsp = "no" *) reg signed [12+SPLIT:0] il, ql, im, qm;
                (* use_dsp = "no" *) reg signed [11+CW-2*SPLIT:0] ih, qh;
                reg signed [11+CW:0] pi, pq;
                always @(posedge clk) begin
                    il <= vi * low; ql <= vq * low;
                    im <= vi * middle; qm <= vq * middle;
                    ih <= vi * high; qh <= vq * high;
                    pi <= $signed(il) + ($signed(im) <<< SPLIT) + ($signed(ih) <<< (2*SPLIT));
                    pq <= $signed(ql) + ($signed(qm) <<< SPLIT) + ($signed(qh) <<< (2*SPLIT));
                end
                assign product_i[k] = $signed({pi, 4'b0});
                assign product_q[k] = $signed({pq, 4'b0});
            end
        end
    endgenerate
    always @(posedge clk) begin
        store_pending <= sample_valid && !reset && write_lane == 2;
        store_group <= write_group;
        valid_pipe <= {valid_pipe[10 : 0], sample_valid && produce};
        output_valid <= valid_pipe[11];
        difference <= $signed({1'b0, write_pointer}) - $signed({1'b0, delay_integer});
        normalized <= difference[AW] ? difference + DEPTH : difference;
        // Exact division by three below 12288. Small lookup tables supply
        // the two halves of the reciprocal product, without using DSP blocks.
        address_low <= address_products[normalized[6:0]];
        address_high <= address_products[normalized[AW-1:7]];
        divided <= {7'd0, address_low} + {address_high, 7'd0};
        normalized_pipe[0] <= normalized;
        normalized_pipe[1] <= normalized_pipe[0];
        first_bank[0] <= first_group[1 : 0];
        first_lane[0] <= normalized_pipe[1] - first_group - (first_group << 1);
        first_bank[1] <= first_bank[0];
        first_lane[1] <= first_lane[0];
        bypass_word[0] <= current_word;
        bypass_lane[0] <= write_lane - delay_integer;
        history_distance <= $signed(filled) - $signed({1'b0, delay_integer});
        for (integer k = 0; k < 8; k = k + 1) begin
            available[1][k] <= !history_distance[AW] && (history_full || history_distance[2:0] >= k);
            bypass[0][k] <= k < 3 && bypass_near && bypass_distance >= k;
        end
        for (integer p = 1; p < 6; p = p + 1) begin
            bypass_word[p] <= bypass_word[p - 1];
            bypass_lane[p] <= bypass_lane[p - 1];
            bypass[p] <= bypass[p - 1];
            if (p > 1) available[p] <= available[p - 1];
        end
        if (sample_valid) begin
            write_pointer <= write_pointer == DEPTH - 1 ? 0 : write_pointer + 1'b1;
            write_lane <= write_lane == 2 ? 0 : write_lane + 1'b1;
            if (write_lane == 2)
                write_group <= write_group + 1'b1;
            partial <= current_word;
            if (filled < DEPTH)
                filled <= filled + 1'b1;
        end
        for (integer k = 0; k < 8; k = k + 1)
            coefficient[k] <= coefficients[k * 18 +: 18];
        for (integer k = 0; k < 4; k = k + 1) begin
            pair_i[k] <= $signed(product_i[2 * k]) + $signed(product_i[2 * k + 1]);
            pair_q[k] <= $signed(product_q[2 * k]) + $signed(product_q[2 * k + 1]);
        end
        for (integer k = 0; k < 2; k = k + 1) begin
            half_i[k] <= $signed(pair_i[2 * k]) + $signed(pair_i[2 * k + 1]);
            half_q[k] <= $signed(pair_q[2 * k]) + $signed(pair_q[2 * k + 1]);
        end
        sum_i <= $signed(half_i[0]) + $signed(half_i[1]);
        sum_q <= $signed(half_q[0]) + $signed(half_q[1]);
        output_i <= ($signed(sum_i) + 37'sd32768) >>> 16;
        output_q <= ($signed(sum_q) + 37'sd32768) >>> 16;
        if (flush) begin
            valid_pipe <= 0;
            output_valid <= 0;
        end
        // Only control state needs reset. Resetting or disabling the arithmetic
        // pipeline would distribute reset to thousands of DSP/adder registers.
        if (reset) begin
            write_pointer <= 0;
            write_group <= 0;
            write_lane <= 0;
            filled <= 0;
            valid_pipe <= 0;
            output_valid <= 0;
            output_i <= 0;
            output_q <= 0;
        end
    end
endmodule
