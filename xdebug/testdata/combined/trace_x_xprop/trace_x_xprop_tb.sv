`timescale 1ns/1ps

interface trace_x_if(input logic clk);
  logic [7:0] data;
  modport source(output data, input clk);
  modport sink(input data, input clk);
endinterface

module trace_x_source(
  input  logic       sel,
  input  logic [7:0] driver_data,
  input  logic [7:0] alternate_data,
  trace_x_if.source  bus
);
  logic [7:0] stage0;
  logic [7:0] stage1;

  always_comb stage0 = driver_data;

  always_comb begin
    if (sel)
      stage1 = stage0;
    else
      stage1 = alternate_data;
  end

  always_comb bus.data = stage1;
endmodule

module trace_x_sink(
  input  logic      rst_n,
  trace_x_if.sink   bus,
  output logic [7:0] observed_q,
  output logic [7:0] observed
);
  always_ff @(posedge bus.clk or negedge rst_n) begin
    if (!rst_n)
      observed_q <= '0;
    else
      observed_q <= bus.data;
  end

  always_comb observed = observed_q;
endmodule

module trace_x_xprop_tb;
  logic       clk;
  logic       rst_n;
  logic       sel;
  logic [7:0] driver_data;
  logic [7:0] alternate_data;
  logic [7:0] observed_q;
  logic [7:0] observed;
  logic [3:0] lookup;
  logic [2:0] lookup_index;
  logic       indexed_out;
  logic [7:0] direct_x_out;
  logic [7:0] multi_rhs_a;
  logic [7:0] multi_rhs_b;
  logic [7:0] multi_rhs_a_mid;
  logic [7:0] multi_rhs_b_mid;
  logic [7:0] multi_rhs_out;
  logic       ctrl_x;
  logic [7:0] ctrl_rhs_data;
  logic [7:0] ctrl_rhs_out;

  trace_x_if link(clk);

  trace_x_source u_source(
    .sel(sel),
    .driver_data(driver_data),
    .alternate_data(alternate_data),
    .bus(link)
  );

  trace_x_sink u_sink(
    .rst_n(rst_n),
    .bus(link),
    .observed_q(observed_q),
    .observed(observed)
  );

  always_comb indexed_out = lookup[lookup_index];
  always_comb direct_x_out = driver_data;
  always_comb multi_rhs_a_mid = multi_rhs_a;
  always_comb multi_rhs_b_mid = multi_rhs_b;
  always_comb multi_rhs_out = multi_rhs_a_mid ^ multi_rhs_b_mid;

  always_comb begin
    if (ctrl_x)
      ctrl_rhs_out = ctrl_rhs_data;
    else
      ctrl_rhs_out = 8'h55;
  end

  initial begin
    clk = 1'b0;
    forever #5 clk = ~clk;
  end

  initial begin
    rst_n = 1'b0;
    sel = 1'b0;
    driver_data = 8'h3c;
    alternate_data = 8'ha5;
    lookup = 4'b1010;
    lookup_index = 3'd1;
    multi_rhs_a = 8'h12;
    multi_rhs_b = 8'h34;
    ctrl_x = 1'b0;
    ctrl_rhs_data = 8'h5a;

    #7 rst_n = 1'b1;
    #3 begin
      sel = 1'bx;              // tmerge: two different branches produce X
      multi_rhs_a = 8'hxx;     // two simultaneous RHS X sources
      multi_rhs_b = 8'hxx;
      ctrl_x = 1'bx;           // control and selected RHS are both X
      ctrl_rhs_data = 8'hxx;
    end
    #10 driver_data = 8'hxx;   // direct driver X
    #10 lookup_index = 3'd7;   // out-of-range bit select produces X
    #20 $finish;
  end
endmodule
