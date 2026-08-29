`ifndef XIF_BASE_TEST_SVH
`define XIF_BASE_TEST_SVH

class xif_base_test extends uvm_test;
  `uvm_component_utils(xif_base_test)

  xif_cfg                    cfg;
  xif_env #(xif_pd_t)        env;
  virtual xif_if #(xif_pd_t) vif;

  function new(string name = "xif_base_test", uvm_component parent = null);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);

    cfg = xif_cfg::type_id::create("cfg");
    env = xif_env #(xif_pd_t)::type_id::create("env", this);

    if (!uvm_config_db#(virtual xif_if #(xif_pd_t))::get(this, "", "vif", vif)) begin
      `uvm_fatal("NOVIF", "test requires virtual interface")
    end

    uvm_config_db#(xif_cfg)::set(this, "env*", "cfg", cfg);
    uvm_config_db#(virtual xif_if #(xif_pd_t))::set(this, "env*", "vif", vif);
    vif.set_cfg(cfg);
  endfunction

  task automatic wait_reset_release();
    wait (vif.rst_n === 1'b1);
    @(posedge vif.clk);
  endtask

  task automatic wait_cycles(int unsigned cycles);
    repeat (cycles) @(posedge vif.clk);
  endtask

  task automatic wait_sampled_handshake();
    do begin
      @(posedge vif.clk);
      #1ns;
    end while (vif.dbg_handshake !== 1'b1);
  endtask

  task automatic wait_for_mon_items(int unsigned count, time timeout = 5000ns);
    int unsigned seen;
    bit timeout_hit;

    fork : wait_mon_fork
      begin
        xif_item #(xif_pd_t) item;
        for (seen = 0; seen < count; seen++) begin
          env.mon_fifo.get(item);
          `uvm_info("MONITEM", item.convert2string(), UVM_MEDIUM)
        end
      end
      begin
        #(timeout);
        timeout_hit = 1'b1;
      end
    join_any
    disable wait_mon_fork;

    if (timeout_hit) begin
      `uvm_fatal("TIMEOUT", $sformatf("Timed out waiting for %0d monitor items", count))
    end
  endtask

  task automatic expect_no_extra_mon_items(int unsigned settle_cycles = 2);
    xif_item #(xif_pd_t) item;

    wait_cycles(settle_cycles);
    if (env.mon_fifo.try_get(item)) begin
      `uvm_fatal("EXTRA_MONITEM", $sformatf("Unexpected extra monitor item: %s", item.convert2string()))
    end
  endtask

  task automatic drive_peer_ready(int unsigned stall_cycles);
    wait_reset_release();
    vif.bp <= 1'b0;
    vif.rdy <= 1'b0;
    wait_cycles(stall_cycles);
    repeat (64) begin
      vif.rdy <= 1'b1;
      @(posedge vif.clk);
    end
  endtask

  task automatic drive_peer_bp(int unsigned stall_cycles);
    wait_reset_release();
    vif.rdy <= 1'b0;
    vif.bp <= 1'b1;
    wait_cycles(stall_cycles);
    repeat (64) begin
      vif.bp <= 1'b0;
      @(posedge vif.clk);
    end
  endtask

  task automatic drive_no_flow_defaults();
    wait_reset_release();
    repeat (32) begin
      vif.rdy <= 1'b0;
      vif.bp <= 1'b0;
      @(posedge vif.clk);
    end
  endtask

  task automatic start_master_sequence(int unsigned num_items = 3);
    xif_smoke_seq seq;

    wait_reset_release();
    seq = xif_smoke_seq::type_id::create("seq");
    seq.num_items = num_items;
    seq.start(env.agent.sequencer);
  endtask

  task automatic start_duplicate_sequence(int unsigned num_items = 2);
    xif_duplicate_pd_seq seq;

    wait_reset_release();
    seq = xif_duplicate_pd_seq::type_id::create("seq");
    seq.num_items = num_items;
    seq.start(env.agent.sequencer);
  endtask

  task automatic drive_slave_side_vld(int unsigned cycles);
    xif_pd_t payload;
    int unsigned idx;

    wait_reset_release();
    vif.vld = 1'b0;
    vif.pd = '0;
    wait_cycles(2);

    for (idx = 0; idx < cycles; idx++) begin
      payload.opcode = 8'h80 + idx[7:0];
      payload.data   = 16'h2000 + idx[15:0];
      @(negedge vif.clk);
      vif.vld = 1'b1;
      vif.pd = payload;
      wait_sampled_handshake();
      vif.vld = 1'b0;
    end

    @(negedge vif.clk);
    vif.vld = 1'b0;
  endtask

  task automatic drive_passive_side_items(int unsigned count);
    xif_pd_t payload;
    int unsigned idx;

    wait_reset_release();
    vif.rdy = 1'b1;
    vif.bp = 1'b0;
    vif.vld = 1'b0;
    vif.pd = '0;

    for (idx = 0; idx < count; idx++) begin
      payload.opcode = 8'hc0 + idx[7:0];
      payload.data = 16'h3000 + idx[15:0];
      @(posedge vif.clk);
      #1ns;
      vif.vld = 1'b1;
      vif.pd = payload;
      @(posedge vif.clk);
      #1ns;
      vif.vld = 1'b0;
    end

    @(negedge vif.clk);
    vif.vld = 1'b0;
  endtask
endclass

`endif
