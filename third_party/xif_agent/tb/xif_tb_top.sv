`ifndef XIF_TB_TOP_SV
`define XIF_TB_TOP_SV

module xif_tb_top;
  import uvm_pkg::*;
  import xif_pkg::*;
  import xif_agent_pkg::*;
  import xif_tb_pkg::*;

  logic clk;
  logic rst_n;

  xif_if #(xif_pd_t)     if0 (.clk(clk), .rst_n(rst_n));
  xif_if #(xif_pd_t)     if_master (.clk(clk), .rst_n(rst_n));
  xif_if #(xif_pd_t)     if_slave (.clk(clk), .rst_n(rst_n));

  logic    link_master_vld;
  xif_pd_t link_master_pd;
  logic    link_slave_rdy;
  logic    link_slave_bp;
  logic    link_slave_vld;
  xif_pd_t link_slave_pd;
  logic    link_master_rdy;
  logic    link_master_bp;

  xif_pair_link_wrapper #(xif_pd_t) u_xif_pair_link_wrapper (
    .master_vld_i(link_master_vld),
    .master_pd_i (link_master_pd),
    .slave_rdy_i (link_slave_rdy),
    .slave_bp_i  (link_slave_bp),
    .slave_vld_o (link_slave_vld),
    .slave_pd_o  (link_slave_pd),
    .master_rdy_o(link_master_rdy),
    .master_bp_o (link_master_bp)
  );
`ifdef XIF_COMPILE_CHECK
  xif_if #(xif_alt_pd_t) if_compile_only (.clk(clk), .rst_n(rst_n));

  xif_alt_item_t      alt_item_h;
  xif_alt_sequencer_t alt_seq_h;
  xif_alt_driver_t    alt_drv_h;
  xif_alt_monitor_t   alt_mon_h;
  xif_alt_agent_t     alt_agent_h;
  xif_alt_env_t       alt_env_h;
`endif

  initial begin
    clk = 1'b0;
    forever #5ns clk = ~clk;
  end

  initial begin
    rst_n = 1'b0;
    repeat (5) @(posedge clk);
    rst_n = 1'b1;
  end

  assign link_master_vld = if_master.vld;
  assign link_master_pd  = if_master.pd;
  assign link_slave_rdy  = if_slave.rdy;
  assign link_slave_bp   = if_slave.bp;

  initial begin
    force if_slave.vld  = link_slave_vld;
    force if_slave.pd   = link_slave_pd;
    force if_master.rdy = link_master_rdy;
    force if_master.bp  = link_master_bp;
  end

  initial begin
    string testname;
    string fsdb_name;

    if (!$value$plusargs("UVM_TESTNAME=%s", testname)) begin
      testname = "xif_default_test";
    end

    fsdb_name = $sformatf("waves/%s.fsdb", testname);
    $fsdbDumpfile(fsdb_name);
    $fsdbDumpvars(0, xif_tb_top, "+all");

    uvm_config_db#(virtual xif_if #(xif_pd_t))::set(null, "uvm_test_top", "vif", if0);
    uvm_config_db#(virtual xif_if #(xif_pd_t))::set(null, "uvm_test_top", "master_vif", if_master);
    uvm_config_db#(virtual xif_if #(xif_pd_t))::set(null, "uvm_test_top", "slave_vif", if_slave);
    run_test();
  end
endmodule

`endif
