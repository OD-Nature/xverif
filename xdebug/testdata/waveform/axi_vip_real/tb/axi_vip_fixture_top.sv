`timescale 1ns/1ps

module axi_vip_fixture_top;
  import uvm_pkg::*;
  import svt_uvm_pkg::*;
  import svt_axi_uvm_pkg::*;

  parameter int simulation_cycle = 10;
  bit clk;
  bit rst_n;

  initial begin
    clk = 0;
    forever #(simulation_cycle / 2) clk = ~clk;
  end

  initial begin
    rst_n = 0;
    repeat (20) @(posedge clk);
    rst_n = 1;
  end

  svt_axi_if axi_vip_if();
  integer axi_oracle_fd;
  bit aw_valid_active, w_valid_active, ar_valid_active, r_valid_active;
  time aw_valid_begin_time, w_valid_begin_time, ar_valid_begin_time, r_valid_begin_time;
  assign axi_vip_if.common_aclk = clk;
  assign axi_vip_if.master_if[0].aresetn = rst_n;
  assign axi_vip_if.slave_if[0].aresetn = rst_n;

  axi_dut_wrapper dut_wrapper (
    .clk(clk),
    .rst_n(rst_n),
    .axi_if(axi_vip_if)
  );

  initial begin
    axi_oracle_fd = $fopen("axi_handshake.jsonl", "w");
    if (axi_oracle_fd == 0)
      `uvm_fatal("ORACLE", "Unable to open axi_handshake.jsonl")
  end

  // Raw channel-handshake oracle.  It intentionally observes pins instead of
  // consuming xdebug or VIP transaction objects, so pytest can reconstruct an
  // independent transaction truth set (including W-before-AW).
  always @(posedge clk) begin
    if (!rst_n) begin
      aw_valid_active = 0;
      w_valid_active = 0;
      ar_valid_active = 0;
      r_valid_active = 0;
    end else begin
      if (!axi_vip_if.master_if[0].awvalid)
        aw_valid_active = 0;
      else if (!aw_valid_active) begin
        aw_valid_active = 1;
        aw_valid_begin_time = $time;
      end
      if (!axi_vip_if.master_if[0].wvalid)
        w_valid_active = 0;
      else if (!w_valid_active) begin
        w_valid_active = 1;
        w_valid_begin_time = $time;
      end
      if (!axi_vip_if.master_if[0].arvalid)
        ar_valid_active = 0;
      else if (!ar_valid_active) begin
        ar_valid_active = 1;
        ar_valid_begin_time = $time;
      end
      if (!axi_vip_if.master_if[0].rvalid)
        r_valid_active = 0;
      else if (!r_valid_active) begin
        r_valid_active = 1;
        r_valid_begin_time = $time;
      end

      if (axi_vip_if.master_if[0].awvalid && axi_vip_if.master_if[0].awready)
        $fdisplay(axi_oracle_fd, "{\"channel\":\"AW\",\"time_ps\":%0t,\"valid_begin_time_ps\":%0t,\"id\":%0d,\"addr\":%0d,\"len\":%0d}",
                 $time, aw_valid_begin_time, axi_vip_if.master_if[0].awid,
                 axi_vip_if.master_if[0].awaddr, axi_vip_if.master_if[0].awlen);
      if (axi_vip_if.master_if[0].wvalid && axi_vip_if.master_if[0].wready)
        $fdisplay(axi_oracle_fd, "{\"channel\":\"W\",\"time_ps\":%0t,\"valid_begin_time_ps\":%0t,\"last\":%0d}",
                 $time, w_valid_begin_time, axi_vip_if.master_if[0].wlast);
      if (axi_vip_if.master_if[0].bvalid && axi_vip_if.master_if[0].bready)
        $fdisplay(axi_oracle_fd, "{\"channel\":\"B\",\"time_ps\":%0t,\"id\":%0d,\"resp\":%0d}",
                 $time, axi_vip_if.master_if[0].bid, axi_vip_if.master_if[0].bresp);
      if (axi_vip_if.master_if[0].arvalid && axi_vip_if.master_if[0].arready)
        $fdisplay(axi_oracle_fd, "{\"channel\":\"AR\",\"time_ps\":%0t,\"valid_begin_time_ps\":%0t,\"id\":%0d,\"addr\":%0d,\"len\":%0d}",
                 $time, ar_valid_begin_time, axi_vip_if.master_if[0].arid,
                 axi_vip_if.master_if[0].araddr, axi_vip_if.master_if[0].arlen);
      if (axi_vip_if.master_if[0].rvalid && axi_vip_if.master_if[0].rready)
        $fdisplay(axi_oracle_fd, "{\"channel\":\"R\",\"time_ps\":%0t,\"valid_begin_time_ps\":%0t,\"id\":%0d,\"last\":%0d,\"resp\":%0d}",
                 $time, r_valid_begin_time, axi_vip_if.master_if[0].rid,
                 axi_vip_if.master_if[0].rlast, axi_vip_if.master_if[0].rresp);

      if (axi_vip_if.master_if[0].awvalid && axi_vip_if.master_if[0].awready)
        aw_valid_active = 0;
      if (axi_vip_if.master_if[0].wvalid && axi_vip_if.master_if[0].wready)
        w_valid_active = 0;
      if (axi_vip_if.master_if[0].arvalid && axi_vip_if.master_if[0].arready)
        ar_valid_active = 0;
      if (axi_vip_if.master_if[0].rvalid && axi_vip_if.master_if[0].rready)
        r_valid_active = 0;
    end
  end

  initial begin
    $fsdbDumpfile("waves.fsdb");
    $fsdbDumpvars("+all");
    $fsdbDumpSVA();
    $fsdbDumpMDA(0, axi_vip_fixture_top);
  end

  initial begin
    uvm_config_db#(svt_axi_vif)::set(
      uvm_root::get(),
      "uvm_test_top.env.axi_system_env",
      "vif",
      axi_vip_if
    );
    run_test();
  end

  initial begin
    #200ms;
    `uvm_fatal("TIMEOUT", "AXI VIP fixture timeout")
  end
endmodule
