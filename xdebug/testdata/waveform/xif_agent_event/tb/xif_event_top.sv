`ifndef XIF_EVENT_TOP_SV
`define XIF_EVENT_TOP_SV

module xif_event_top;
  import uvm_pkg::*;
  import xif_pkg::*;
  import xif_agent_pkg::*;
  import xif_event_pkg::*;

  logic clk;
  logic rst_n;
  logic xz_vld;
  logic [15:0] xz_data;

  xif_if #(xif_event_pd_t) if_rdy (.clk(clk), .rst_n(rst_n));
  xif_if #(xif_event_pd_t) if_bp (.clk(clk), .rst_n(rst_n));
  xif_if #(xif_event_pd_t) if_none (.clk(clk), .rst_n(rst_n));
  xif_if #(xif_event_pd_t) if_pair_master (.clk(clk), .rst_n(rst_n));
  xif_if #(xif_event_pd_t) if_pair_slave (.clk(clk), .rst_n(rst_n));

  initial begin
    clk = 1'b0;
    forever #5ns clk = ~clk;
  end

  initial begin
    rst_n = 1'b0;
    repeat (5) @(posedge clk);
    rst_n = 1'b1;
  end

  initial begin
    xz_vld = 1'b0;
    xz_data = 16'h0000;
    wait (rst_n === 1'b1);
    repeat (2) @(posedge clk);
    xz_data = 16'hxxxx;
    xz_vld = 1'b1;
    @(posedge clk);
    xz_vld = 1'b0;
    xz_data = 16'h0000;
  end

  initial begin
    force if_pair_slave.vld = if_pair_master.vld;
    force if_pair_slave.pd = if_pair_master.pd;
    force if_pair_master.rdy = if_pair_slave.rdy;
    force if_pair_master.bp = if_pair_slave.bp;
  end

  initial begin
    uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(null, "uvm_test_top", "if_rdy", if_rdy);
    uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(null, "uvm_test_top", "if_bp", if_bp);
    uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(null, "uvm_test_top", "if_none", if_none);
    uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(null, "uvm_test_top", "if_pair_master", if_pair_master);
    uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(null, "uvm_test_top", "if_pair_slave", if_pair_slave);

    run_test();
  end
endmodule

`endif
