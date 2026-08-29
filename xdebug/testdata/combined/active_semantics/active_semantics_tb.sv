`timescale 1ns/1ps

module active_semantics_dut (
  input  logic       clk,
  input  logic       rst_n,
  input  logic       en,
  input  logic       sel,
  input  logic       valid,
  input  logic       ready,
  input  logic       req0,
  input  logic       req1,
  input  logic [7:0] data_a,
  input  logic [7:0] data_b,
  input  logic [7:0] payload,
  input  logic [7:0] payload0,
  input  logic [7:0] payload1,
  input  logic [7:0] chain_src,
  output logic [7:0] q_en,
  output logic [7:0] mux_y,
  output logic [7:0] handshake_q,
  output logic [7:0] arb_q,
  output logic [7:0] chain_out,
  output logic [7:0] ambiguous_rhs_out,
  output wire  [7:0] multiple_driver_out
);

  logic [7:0] chain_mid;

  assign chain_mid = chain_src;       // CHAIN_MID_ASSIGN
  assign chain_out = chain_mid;       // CHAIN_OUT_ASSIGN
  assign ambiguous_rhs_out = data_a ^ data_b; // AMBIGUOUS_RHS_ASSIGN
  assign multiple_driver_out = data_a;        // MULTIPLE_DRIVER_A
  assign multiple_driver_out = data_b ^ 8'h10; // MULTIPLE_DRIVER_B

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      q_en <= 8'h00;                  // RESET_Q_EN
    else if (en)
      q_en <= data_a;                 // ENABLE_Q_EN_DATA
    else
      q_en <= q_en;                   // HOLD_Q_EN
  end

  always_comb begin
    if (sel)
      mux_y = data_a;                 // MUX_ACTIVE_A
    else
      mux_y = data_b;                 // MUX_ACTIVE_B
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      handshake_q <= 8'h00;           // RESET_HANDSHAKE
    else if (valid && ready)
      handshake_q <= payload;         // HANDSHAKE_PAYLOAD
    else
      handshake_q <= handshake_q;     // HANDSHAKE_HOLD
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      arb_q <= 8'h00;                 // RESET_ARB
    else if (req0)
      arb_q <= payload0;              // ARB_WINNER_0
    else if (req1)
      arb_q <= payload1;              // ARB_WINNER_1
    else
      arb_q <= 8'h00;                 // ARB_IDLE
  end
endmodule

module active_semantics_missing_rhs_probe (
  input  logic [7:0] recorded_rhs,
  input  logic [7:0] undumped_rhs,
  output logic [7:0] result
);
  assign result = recorded_rhs ^ undumped_rhs; // MISSING_RHS_ASSIGN
endmodule

module active_semantics_tb;
  logic       clk;
  logic       rst_n;
  logic       en;
  logic       sel;
  logic       valid;
  logic       ready;
  logic       req0;
  logic       req1;
  logic [7:0] data_a;
  logic [7:0] data_b;
  logic [7:0] payload;
  logic [7:0] payload0;
  logic [7:0] payload1;
  logic [7:0] chain_src;
  logic [7:0] q_en;
  logic [7:0] mux_y;
  logic [7:0] handshake_q;
  logic [7:0] arb_q;
  logic [7:0] chain_out;
  logic [7:0] ambiguous_rhs_out;
  wire  [7:0] multiple_driver_out;
  logic [7:0] missing_rhs_out;

  active_semantics_dut u_dut (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .sel(sel),
    .valid(valid),
    .ready(ready),
    .req0(req0),
    .req1(req1),
    .data_a(data_a),
    .data_b(data_b),
    .payload(payload),
    .payload0(payload0),
    .payload1(payload1),
    .chain_src(chain_src),
    .q_en(q_en),
    .mux_y(mux_y),
    .handshake_q(handshake_q),
    .arb_q(arb_q),
    .chain_out(chain_out),
    .ambiguous_rhs_out(ambiguous_rhs_out),
    .multiple_driver_out(multiple_driver_out)
  );

  active_semantics_missing_rhs_probe u_missing_probe (
    .recorded_rhs(data_a),
    .undumped_rhs(data_b),
    .result(missing_rhs_out)
  );

  initial begin
    clk = 1'b0;
    forever #5 clk = ~clk;
  end

  initial begin
    rst_n    = 1'b0;
    en       = 1'b0;
    sel      = 1'b0;
    valid    = 1'b0;
    ready    = 1'b0;
    req0     = 1'b0;
    req1     = 1'b0;
    data_a   = 8'hA0;
    data_b   = 8'hB0;
    payload  = 8'h10;
    payload0 = 8'hC0;
    payload1 = 8'hD0;
    chain_src = 8'h30;

    #12;
    rst_n = 1'b1;
    en = 1'b1;           // q_en captures data_a at 15ns
    sel = 1'b1;          // mux_y follows data_a
    valid = 1'b1;
    ready = 1'b1;        // handshake_q captures payload at 15ns
    req0 = 1'b1;         // arb_q captures payload0 at 15ns

    #10;
    en = 1'b0;           // q_en holds at 25ns even though data_a changes
    sel = 1'b0;          // mux_y follows data_b
    ready = 1'b0;        // handshake_q holds at 25ns even though payload changes
    req0 = 1'b0;
    req1 = 1'b1;         // arb_q captures payload1 at 25ns
    data_a = 8'hA1;
    data_b = 8'hB2;
    payload = 8'h11;
    payload0 = 8'hC1;
    payload1 = 8'hD1;
    chain_src = 8'h31;    // CHAIN_SRC_DRIVE

    #10;
    en = 1'b1;           // q_en captures new data_a at 35ns
    valid = 1'b1;
    ready = 1'b1;        // handshake_q captures new payload at 35ns
    req0 = 1'b0;
    req1 = 1'b0;         // arb_q takes idle at 35ns
    data_a = 8'hx2;
    data_b = 8'hB3;
    payload = 8'h12;
    payload1 = 8'hD2;
    chain_src = 8'h32;

    #20;
    $finish;
  end
endmodule
