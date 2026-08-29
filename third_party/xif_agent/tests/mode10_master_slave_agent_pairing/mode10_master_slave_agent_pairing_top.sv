`ifndef MODE10_MASTER_SLAVE_AGENT_PAIRING_TOP_SV
`define MODE10_MASTER_SLAVE_AGENT_PAIRING_TOP_SV

module mode10_master_slave_agent_pairing_top;
  import uvm_pkg::*;
  import xif_pkg::*;
  import xif_agent_pkg::*;
  import mode10_master_slave_agent_pairing_pkg::*;

  logic clk;
  logic rst_n;

  xif_if #(mode10_pd_t) if_master (.clk(clk), .rst_n(rst_n));
  xif_if #(mode10_pd_t) if_slave  (.clk(clk), .rst_n(rst_n));

  logic       link_master_vld;
  mode10_pd_t link_master_pd;
  logic       link_slave_rdy;
  logic       link_slave_bp;
  logic       link_slave_vld;
  mode10_pd_t link_slave_pd;
  logic       link_master_rdy;
  logic       link_master_bp;

  xif_pair_link_wrapper #(mode10_pd_t) u_xif_pair_link_wrapper (
    .master_vld_i(link_master_vld),
    .master_pd_i (link_master_pd),
    .slave_rdy_i (link_slave_rdy),
    .slave_bp_i  (link_slave_bp),
    .slave_vld_o (link_slave_vld),
    .slave_pd_o  (link_slave_pd),
    .master_rdy_o(link_master_rdy),
    .master_bp_o (link_master_bp)
  );

  assign link_master_vld = if_master.vld;
  assign link_master_pd  = if_master.pd;
  assign link_slave_rdy  = if_slave.rdy;
  assign link_slave_bp   = if_slave.bp;

  // Keep force on xif_if targets to avoid multi-driver conflicts with the
  // interface's internal initial block drivers.
  initial begin
    force if_slave.vld  = link_slave_vld;
    force if_slave.pd   = link_slave_pd;
    force if_master.rdy = link_master_rdy;
    force if_master.bp  = link_master_bp;
  end

  // Clock generation
  initial begin
    clk = 1'b0;
    forever #5ns clk = ~clk;
  end

  // Reset generation
  initial begin
    rst_n = 1'b0;
    repeat (5) @(posedge clk);
    rst_n = 1'b1;
  end

  // FSDB dump and test launch
  initial begin
    string testname;
    string fsdb_name;

    if (!$value$plusargs("UVM_TESTNAME=%s", testname)) begin
      testname = "mode10_master_slave_agent_pairing_test";
    end

    fsdb_name = $sformatf("waves/%s.fsdb", testname);
    $fsdbDumpfile(fsdb_name);
    $fsdbDumpvars(0, mode10_master_slave_agent_pairing_top, "+all");

    uvm_config_db#(virtual xif_if #(mode10_pd_t))::set(null, "uvm_test_top", "master_vif", if_master);
    uvm_config_db#(virtual xif_if #(mode10_pd_t))::set(null, "uvm_test_top", "slave_vif", if_slave);
    run_test();
  end
endmodule

`endif
