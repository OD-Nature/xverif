`timescale 1ns/1ps

interface data_if(input logic clk);
  logic [7:0] data;

  modport source(output data, input clk);
  modport sink(input data, input clk);
endinterface

module if_source (
  input  logic       rst_n,
  input  logic       sel,
  input  logic [7:0] a,
  input  logic [7:0] b,
  data_if.source     bus
);
  always_ff @(posedge bus.clk or negedge rst_n) begin
    if (!rst_n)
      bus.data <= 8'h00;
    else if (sel)
      bus.data <= a;
    else
      bus.data <= b;
  end
endmodule

module if_sink (
  input  logic   rst_n,
  data_if.sink   bus,
  output logic [7:0] observed_q
);
  always_ff @(posedge bus.clk or negedge rst_n) begin
    if (!rst_n)
      observed_q <= 8'h00;
    else
      observed_q <= bus.data;
  end
endmodule

module if_root_tb;
  logic       clk;
  logic       rst_n;
  logic       sel;
  logic [7:0] a;
  logic [7:0] b;
  logic [7:0] observed_q;

  data_if link(clk);

  if_source u_src (
    .rst_n(rst_n),
    .sel(sel),
    .a(a),
    .b(b),
    .bus(link)
  );

  if_sink u_sink (
    .rst_n(rst_n),
    .bus(link),
    .observed_q(observed_q)
  );

  initial begin
    clk = 1'b0;
    forever #5 clk = ~clk;
  end

  initial begin
    rst_n = 1'b0;
    sel   = 1'b0;
    a     = 8'hA5;
    b     = 8'h5A;

    #7;
    rst_n = 1'b1;
    sel   = 1'b1;  // u_src drives link.data <= a at 15ns

    #10;
    sel = 1'b0;    // u_src drives link.data <= b at 25ns

    #20;
    $finish;
  end
endmodule
