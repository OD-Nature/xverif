`timescale 1ns/1ps

module primitive_output_dut (
  input data_i,
  input enable_i,
  output out_bufif
);
  bufif1 b1(out_bufif, data_i, enable_i);
endmodule

module reduction_output_dut #(
  parameter C_VEC_NUM = 4
) (
  input clk,
  input rst_n,
  input [C_VEC_NUM-1:0] sample_vec_next,
  output reg sample_flag
);
  wire sample_flag_expr;
  reg [C_VEC_NUM-1:0] sample_vec_q;

  assign sample_flag_expr = |sample_vec_q;

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      sample_vec_q <= {C_VEC_NUM{1'b0}};
    end else begin
      sample_vec_q <= sample_vec_next;
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      sample_flag <= 1'b0;
    end else begin
      sample_flag <= sample_flag_expr;
    end
  end
endmodule

module reduction_active_time_probe (
  output reg sample_flag
);
  reg clk;
  reg rst_n;
  reg [3:0] sample_vec_next;
  reg [3:0] sample_vec_q;
  wire sample_flag_expr;

  assign sample_flag_expr = |sample_vec_q;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    sample_vec_next = 4'b0000;
    sample_vec_q = 4'b0000;
    #2 rst_n = 1'b1;
    #1 sample_vec_next = 4'b0001;
    #2 clk = 1'b1;
    #1 clk = 1'b0;
    #4 clk = 1'b1;
    #5 clk = 1'b0;
  end

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      sample_vec_q <= 4'b0000;
    end else begin
      sample_vec_q <= sample_vec_next;
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      sample_flag <= 1'b0;
    end else begin
      sample_flag <= sample_flag_expr;
    end
  end
endmodule

module reduction_cycle_pulse_probe (
  output reg sample_flag
);
  reg clk;
  reg rst_n;
  integer cycle_count;
  reg [3:0] sample_vec_next;
  reg [3:0] sample_vec_q;
  wire sample_flag_expr;

  assign sample_flag_expr = |sample_vec_q;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    #2 rst_n = 1'b1;
  end

  always #5 clk = ~clk;

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      cycle_count <= 0;
      sample_vec_next <= 4'b0000;
    end else begin
      cycle_count <= cycle_count + 1;
      if (cycle_count == 7) begin
        sample_vec_next <= 4'b0001;
      end else if (cycle_count == 8) begin
        sample_vec_next <= 4'b0000;
      end
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      sample_vec_q <= 4'b0000;
    end else begin
      sample_vec_q <= sample_vec_next;
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      sample_flag <= 1'b0;
    end else begin
      sample_flag <= sample_flag_expr;
    end
  end
endmodule

module reduction_us_pulse_probe (
  output reg sample_flag
);
  reg clk;
  reg rst_n;
  reg [3:0] sample_vec_next;
  reg [3:0] sample_vec_q;
  wire sample_flag_expr;

  assign sample_flag_expr = |sample_vec_q;

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    sample_vec_next = 4'b0000;
    #2 rst_n = 1'b1;
    #9968 sample_vec_next = 4'b0001;
    #10 sample_vec_next = 4'b0000;
  end

  always #5 clk = ~clk;

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      sample_vec_q <= 4'b0000;
    end else begin
      sample_vec_q <= sample_vec_next;
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      sample_flag <= 1'b0;
    end else begin
      sample_flag <= sample_flag_expr;
    end
  end
endmodule

module reduction_active_time_no_reset_probe (
  output reg sample_flag
);
  reg clk;
  reg [3:0] sample_vec_q;
  wire sample_flag_expr;

  assign sample_flag_expr = |sample_vec_q;

  initial begin
    clk = 1'b0;
    sample_vec_q = 4'b0001;
    sample_flag = 1'b0;
    #10 clk = 1'b1;
    #5 clk = 1'b0;
  end

  always @(posedge clk) begin
    sample_flag <= sample_flag_expr;
  end
endmodule

module input_trace_child (
  input clk,
  input rst_n,
  input data_i,
  output reg data_q
);
  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      data_q <= 1'b0;
    end else begin
      data_q <= data_i;
    end
  end
endmodule

module expr_zero_evidence_dut #(
  parameter W = 4
) (
  input clk,
  input rst_n,
  input [W-1:0] vec_a_next,
  input [W-1:0] vec_b_next,
  input [W-1:0] mask_next,
  input valid_next,
  input ready_next,
  input enable_next,
  input flush_next,
  input [1:0] idx_next,
  output reg q_reduce_or,
  output reg q_reduce_and,
  output reg q_reduce_xor,
  output reg q_bit_or_ne0,
  output reg q_bit_and_ne0,
  output reg q_xor_reduce_mask,
  output reg q_logic_and,
  output reg q_logic_or,
  output reg q_reduce_and_enable,
  output reg q_ternary_reduce,
  output reg q_compare_ne0,
  output reg q_compare_eq_const,
  output reg q_compare_gt,
  output reg q_bit_select,
  output reg q_const_part_reduce,
  output reg q_indexed_part_reduce,
  output reg q_concat_reduce,
  output reg q_nested_mix
);
  reg [W-1:0] vec_a_r;
  reg [W-1:0] vec_b_r;
  reg [W-1:0] mask_r;
  reg valid_r;
  reg ready_r;
  reg enable_r;
  reg flush_r;
  reg [1:0] idx_r;

  wire cb_reduce_or = |vec_a_r;
  wire cb_reduce_and = &vec_a_r;
  wire cb_reduce_xor = ^vec_a_r;
  wire cb_bit_or_ne0 = (vec_a_r | vec_b_r) != {W{1'b0}};
  wire cb_bit_and_ne0 = (vec_a_r & mask_r) != {W{1'b0}};
  wire cb_xor_reduce_mask = ^(vec_a_r & mask_r);
  wire cb_logic_and = valid_r && ready_r;
  wire cb_logic_or = valid_r || ready_r;
  wire cb_reduce_and_enable = (|vec_a_r) && enable_r;
  wire cb_ternary_reduce = enable_r ? (|vec_a_r) : 1'b0;
  wire cb_compare_ne0 = vec_a_r != {W{1'b0}};
  wire cb_compare_eq_const = vec_a_r == 4'b1000;
  wire cb_compare_gt = vec_a_r > vec_b_r;
  wire cb_bit_select = vec_a_r[idx_r];
  wire cb_const_part_reduce = |vec_a_r[2:0];
  wire cb_indexed_part_reduce = |vec_a_r[idx_r +: 2];
  wire cb_concat_reduce = |{valid_r, vec_a_r[2:0], ready_r};
  wire cb_nested_mix = ((|vec_a_r) && enable_r) || (ready_r && !flush_r);

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      vec_a_r <= {W{1'b0}};
      vec_b_r <= {W{1'b0}};
      mask_r <= {W{1'b0}};
      valid_r <= 1'b0;
      ready_r <= 1'b0;
      enable_r <= 1'b0;
      flush_r <= 1'b0;
      idx_r <= 2'b00;
    end else begin
      vec_a_r <= vec_a_next;
      vec_b_r <= vec_b_next;
      mask_r <= mask_next;
      valid_r <= valid_next;
      ready_r <= ready_next;
      enable_r <= enable_next;
      flush_r <= flush_next;
      idx_r <= idx_next;
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      q_reduce_or <= 1'b0;
      q_reduce_and <= 1'b0;
      q_reduce_xor <= 1'b0;
      q_bit_or_ne0 <= 1'b0;
      q_bit_and_ne0 <= 1'b0;
      q_xor_reduce_mask <= 1'b0;
      q_logic_and <= 1'b0;
      q_logic_or <= 1'b0;
      q_reduce_and_enable <= 1'b0;
      q_ternary_reduce <= 1'b0;
      q_compare_ne0 <= 1'b0;
      q_compare_eq_const <= 1'b0;
      q_compare_gt <= 1'b0;
      q_bit_select <= 1'b0;
      q_const_part_reduce <= 1'b0;
      q_indexed_part_reduce <= 1'b0;
      q_concat_reduce <= 1'b0;
      q_nested_mix <= 1'b0;
    end else begin
      q_reduce_or <= cb_reduce_or;
      q_reduce_and <= cb_reduce_and;
      q_reduce_xor <= cb_reduce_xor;
      q_bit_or_ne0 <= cb_bit_or_ne0;
      q_bit_and_ne0 <= cb_bit_and_ne0;
      q_xor_reduce_mask <= cb_xor_reduce_mask;
      q_logic_and <= cb_logic_and;
      q_logic_or <= cb_logic_or;
      q_reduce_and_enable <= cb_reduce_and_enable;
      q_ternary_reduce <= cb_ternary_reduce;
      q_compare_ne0 <= cb_compare_ne0;
      q_compare_eq_const <= cb_compare_eq_const;
      q_compare_gt <= cb_compare_gt;
      q_bit_select <= cb_bit_select;
      q_const_part_reduce <= cb_const_part_reduce;
      q_indexed_part_reduce <= cb_indexed_part_reduce;
      q_concat_reduce <= cb_concat_reduce;
      q_nested_mix <= cb_nested_mix;
    end
  end
endmodule

module active_zero_evidence_tb (
  input top_input_i
);
  reg clk;
  reg rst_n;
  reg data_i;
  reg enable_i;
  wire out_bufif;
  reg [3:0] sample_vec_next;
  wire sample_flag;
  wire sample_flag_10ns;
  wire sample_flag_cycle_pulse;
  wire sample_flag_us_pulse;
  reg parent_src_next;
  reg parent_src;
  wire child_data_q;
  wire top_input_tap;
  reg [3:0] vec_a_next;
  reg [3:0] vec_b_next;
  reg [3:0] mask_next;
  reg valid_next;
  reg ready_next;
  reg expr_enable_next;
  reg flush_next;
  reg [1:0] idx_next;
  wire q_reduce_or;
  wire q_reduce_and;
  wire q_reduce_xor;
  wire q_bit_or_ne0;
  wire q_bit_and_ne0;
  wire q_xor_reduce_mask;
  wire q_logic_and;
  wire q_logic_or;
  wire q_reduce_and_enable;
  wire q_ternary_reduce;
  wire q_compare_ne0;
  wire q_compare_eq_const;
  wire q_compare_gt;
  wire q_bit_select;
  wire q_const_part_reduce;
  wire q_indexed_part_reduce;
  wire q_concat_reduce;
  wire q_nested_mix;

  primitive_output_dut u_primitive (
    .data_i(data_i),
    .enable_i(enable_i),
    .out_bufif(out_bufif)
  );

  reduction_output_dut #(.C_VEC_NUM(4)) u_reduction (
    .clk(clk),
    .rst_n(rst_n),
    .sample_vec_next(sample_vec_next),
    .sample_flag(sample_flag)
  );

  reduction_active_time_probe u_reduction_10ns (
    .sample_flag(sample_flag_10ns)
  );

  reduction_cycle_pulse_probe u_reduction_cycle_pulse (
    .sample_flag(sample_flag_cycle_pulse)
  );

  reduction_us_pulse_probe u_reduction_us_pulse (
    .sample_flag(sample_flag_us_pulse)
  );

  input_trace_child u_input_child (
    .clk(clk),
    .rst_n(rst_n),
    .data_i(parent_src),
    .data_q(child_data_q)
  );

  expr_zero_evidence_dut u_expr (
    .clk(clk),
    .rst_n(rst_n),
    .vec_a_next(vec_a_next),
    .vec_b_next(vec_b_next),
    .mask_next(mask_next),
    .valid_next(valid_next),
    .ready_next(ready_next),
    .enable_next(expr_enable_next),
    .flush_next(flush_next),
    .idx_next(idx_next),
    .q_reduce_or(q_reduce_or),
    .q_reduce_and(q_reduce_and),
    .q_reduce_xor(q_reduce_xor),
    .q_bit_or_ne0(q_bit_or_ne0),
    .q_bit_and_ne0(q_bit_and_ne0),
    .q_xor_reduce_mask(q_xor_reduce_mask),
    .q_logic_and(q_logic_and),
    .q_logic_or(q_logic_or),
    .q_reduce_and_enable(q_reduce_and_enable),
    .q_ternary_reduce(q_ternary_reduce),
    .q_compare_ne0(q_compare_ne0),
    .q_compare_eq_const(q_compare_eq_const),
    .q_compare_gt(q_compare_gt),
    .q_bit_select(q_bit_select),
    .q_const_part_reduce(q_const_part_reduce),
    .q_indexed_part_reduce(q_indexed_part_reduce),
    .q_concat_reduce(q_concat_reduce),
    .q_nested_mix(q_nested_mix)
  );

  assign top_input_tap = top_input_i;

  initial begin
    clk = 1'b0;
    forever #5 clk = ~clk;
  end

  initial begin
    rst_n = 1'b0;
    data_i = 1'b0;
    enable_i = 1'b0;
    sample_vec_next = 4'b0000;
    parent_src_next = 1'b0;
    parent_src = 1'b0;
    vec_a_next = 4'b0000;
    vec_b_next = 4'b0000;
    mask_next = 4'b0000;
    valid_next = 1'b0;
    ready_next = 1'b0;
    expr_enable_next = 1'b0;
    flush_next = 1'b0;
    idx_next = 2'b00;

    #7 rst_n = 1'b1;
    #3 sample_vec_next = 4'b0001;
       vec_a_next = 4'b0001;
       vec_b_next = 4'b0010;
       mask_next = 4'b0101;
       valid_next = 1'b1;
       ready_next = 1'b0;
       expr_enable_next = 1'b1;
       parent_src_next = 1'b1;
       idx_next = 2'b00;
    #5 enable_i = 1'b1;
    #5 sample_vec_next = 4'b0000;
       parent_src_next = 1'b0;
       vec_a_next = 4'b0000;
       vec_b_next = 4'b1000;
       mask_next = 4'b1111;
       valid_next = 1'b1;
       ready_next = 1'b1;
       expr_enable_next = 1'b0;
       idx_next = 2'b01;
    #10 sample_vec_next = 4'b1000;
        parent_src_next = 1'b1;
        vec_a_next = 4'b1000;
        vec_b_next = 4'b0011;
        mask_next = 4'b1010;
        valid_next = 1'b0;
        ready_next = 1'b1;
        expr_enable_next = 1'b1;
        flush_next = 1'b0;
        idx_next = 2'b10;
    #10 sample_vec_next = 4'b0000;
        vec_a_next = 4'b0110;
        vec_b_next = 4'b0101;
        mask_next = 4'b0011;
        valid_next = 1'b1;
        ready_next = 1'b1;
        expr_enable_next = 1'b1;
        flush_next = 1'b1;
        idx_next = 2'b01;
    #10060 $finish;
  end

  always @(posedge clk or negedge rst_n) begin
    if (~rst_n) begin
      parent_src <= 1'b0;
    end else begin
      parent_src <= parent_src_next;
    end
  end
endmodule
