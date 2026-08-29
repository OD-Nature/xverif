`ifndef MODE04_BURST_TOP_SV
`define MODE04_BURST_TOP_SV

module mode04_burst_top;
  import uvm_pkg::*;
  import xif_pkg::*;
  import xif_agent_pkg::*;
  import mode04_burst_pkg::*;

  logic clk;
  logic rst_n;

  xif_if #(mode04_pd_t) xif0 (.clk(clk), .rst_n(rst_n));

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
      testname = "mode04_burst_test";
    end

    fsdb_name = $sformatf("waves/%s.fsdb", testname);
    $fsdbDumpfile(fsdb_name);
    $fsdbDumpvars(0, mode04_burst_top, "+all");

    uvm_config_db#(virtual xif_if #(mode04_pd_t))::set(null, "uvm_test_top", "vif", xif0);
    run_test();
  end
endmodule

`endif
