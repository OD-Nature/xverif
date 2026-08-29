`ifndef MODE01_BASIC_DRIVE_PKG_SV
`define MODE01_BASIC_DRIVE_PKG_SV

package mode01_basic_drive_pkg;
  import uvm_pkg::*;
  import xif_pkg::*;
  import xif_agent_pkg::*;
  `include "uvm_macros.svh"

  // ============================
  // PD_T definition
  // ============================
  typedef struct packed {
    logic [7:0]  opcode;
    logic [15:0] data;
  } mode01_pd_t;

  // ============================
  // Environment
  // ============================
  class mode01_env #(type PD_T = mode01_pd_t) extends uvm_env;
    `uvm_component_param_utils(mode01_env #(PD_T))

    xif_agent #(PD_T)                         agent;
    uvm_tlm_analysis_fifo #(xif_item #(PD_T)) mon_fifo;

    function new(string name = "mode01_env", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      agent = xif_agent #(PD_T)::type_id::create("agent", this);
      mon_fifo = new("mon_fifo", this);
    endfunction

    function void connect_phase(uvm_phase phase);
      super.connect_phase(phase);
      agent.ap.connect(mon_fifo.analysis_export);
    endfunction
  endclass

  // ============================
  // Basic drive sequence
  // ============================
  class mode01_basic_seq extends uvm_sequence #(xif_item #(mode01_pd_t));
    rand int unsigned num_items;

    `uvm_object_utils(mode01_basic_seq)

    function new(string name = "mode01_basic_seq");
      super.new(name);
      num_items = 5;
    endfunction

    task body();
      xif_item #(mode01_pd_t) req;
      int unsigned idx;

      for (idx = 0; idx < num_items; idx++) begin
        mode01_pd_t payload;
        payload.opcode = 8'h10 + idx[7:0];
        payload.data   = 16'h1000 + idx[15:0];

        req = xif_item #(mode01_pd_t)::type_id::create($sformatf("req_%0d", idx));
        req.pd = payload;
        req.leading_cycles = (idx % 5);
        req.post_cycles = ((idx % 2) == 0) ? 1 : 2;

        `uvm_info("MODE01_SEQ", $sformatf("sending item %s", req.convert2string()), UVM_MEDIUM)
        start_item(req);
        finish_item(req);
      end
    endtask
  endclass

  // ============================
  // Base test with helpers
  // ============================
  class mode01_base_test extends uvm_test;
    `uvm_component_utils(mode01_base_test)

    xif_cfg                           cfg;
    mode01_env #(mode01_pd_t)         env;
    virtual xif_if #(mode01_pd_t)     vif;

    function new(string name = "mode01_base_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg = xif_cfg::type_id::create("cfg");
      env = mode01_env #(mode01_pd_t)::type_id::create("env", this);
      if (!uvm_config_db#(virtual xif_if #(mode01_pd_t))::get(this, "", "vif", vif)) begin
        `uvm_fatal("NOVIF", "test requires virtual interface")
      end
      uvm_config_db#(xif_cfg)::set(this, "env*", "cfg", cfg);
      uvm_config_db#(virtual xif_if #(mode01_pd_t))::set(this, "env*", "vif", vif);
      vif.set_cfg(cfg);
    endfunction

    task automatic wait_reset_release();
      wait (vif.rst_n === 1'b1);
      @(posedge vif.clk);
    endtask

    task automatic wait_cycles(int unsigned cycles);
      repeat (cycles) @(posedge vif.clk);
    endtask

    task automatic wait_for_mon_items(int unsigned count, time timeout = 5000ns);
      int unsigned seen;
      bit timeout_hit;
      fork : wait_mon_fork
        begin
          xif_item #(mode01_pd_t) item;
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
      xif_item #(mode01_pd_t) item;
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
      repeat (128) begin
        vif.rdy <= 1'b1;
        @(posedge vif.clk);
      end
    endtask
  endclass

  // ============================
  // Concrete test
  // ============================
  class mode01_basic_drive_test extends mode01_base_test;
    `uvm_component_utils(mode01_basic_drive_test)

    function new(string name = "mode01_basic_drive_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg.active_passive = UVM_ACTIVE;
      cfg.role = XIF_ROLE_MASTER;
      cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
      cfg.timeout_cycles = 8;
    endfunction

    task run_phase(uvm_phase phase);
      mode01_basic_seq seq;

      phase.raise_objection(this);
      fork
        drive_peer_ready(2);
      join_none

      wait_reset_release();
      seq = mode01_basic_seq::type_id::create("seq");
      seq.num_items = 5;
      seq.start(env.agent.sequencer);

      wait_for_mon_items(5);
      expect_no_extra_mon_items();
      phase.drop_objection(this);
    endtask
  endclass

endpackage

`endif
