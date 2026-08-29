`ifndef MODE08_REACTION_SEQUENCES_TOP_SV
`define MODE08_REACTION_SEQUENCES_TOP_SV

module mode08_reaction_sequences_top;
  import uvm_pkg::*;
  import xif_pkg::*;
  import xif_agent_pkg::*;
  import mode08_reaction_sequences_pkg::*;

  logic clk;
  logic rst_n;

  xif_if #(mode08_pd_t) if_A (.clk(clk), .rst_n(rst_n));
  xif_if #(mode08_pd_t) if_B (.clk(clk), .rst_n(rst_n));

  logic       link_src_vld;
  mode08_pd_t link_src_pd;
  logic       link_src_rdy;
  logic       link_dst_vld;
  mode08_pd_t link_dst_pd;
  logic       link_dst_rdy;

  xif_observe_link_wrapper #(mode08_pd_t) u_xif_observe_link_wrapper (
    .src_vld_i(link_src_vld),
    .src_pd_i (link_src_pd),
    .src_rdy_i(link_src_rdy),
    .dst_vld_o(link_dst_vld),
    .dst_pd_o (link_dst_pd),
    .dst_rdy_o(link_dst_rdy)
  );

  assign link_src_vld = if_A.vld;
  assign link_src_pd  = if_A.pd;
  assign link_src_rdy = if_A.rdy;

  // Keep force on xif_if targets to avoid multi-driver conflicts with the
  // interface's internal initial block drivers.
  initial begin
    force if_B.vld = link_dst_vld;
    force if_B.pd  = link_dst_pd;
    force if_B.rdy = link_dst_rdy;
  end

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
    string testname;
    string fsdb_name;

    if (!$value$plusargs("UVM_TESTNAME=%s", testname)) begin
      testname = "mode08_reaction_sequences_test";
    end

    fsdb_name = $sformatf("waves/%s.fsdb", testname);
    $fsdbDumpfile(fsdb_name);
    $fsdbDumpvars(0, mode08_reaction_sequences_top, "+all");

    uvm_config_db#(virtual xif_if #(mode08_pd_t))::set(null, "uvm_test_top", "vif_A", if_A);
    uvm_config_db#(virtual xif_if #(mode08_pd_t))::set(null, "uvm_test_top", "vif_B", if_B);
    run_test();
  end
endmodule

`endif
