`ifndef MODE08_REACTION_SEQUENCES_PKG_SV
`define MODE08_REACTION_SEQUENCES_PKG_SV

package mode08_reaction_sequences_pkg;
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
  } mode08_pd_t;

  // ============================
  // Environment — TWO agents:
  // agent_A (MASTER) drives stimulus
  // agent_B (PASSIVE) monitors for cross-interface reaction
  // ============================
  class mode08_env #(type PD_T = mode08_pd_t) extends uvm_env;
    `uvm_component_param_utils(mode08_env #(PD_T))

    xif_agent #(PD_T)                         agent_A;
    xif_agent #(PD_T)                         agent_B;
    uvm_tlm_analysis_fifo #(xif_item #(PD_T)) agent_A_mon_fifo;
    uvm_tlm_analysis_fifo #(xif_item #(PD_T)) agent_B_mon_fifo;

    function new(string name = "mode08_env", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      agent_A = xif_agent #(PD_T)::type_id::create("agent_A", this);
      agent_B = xif_agent #(PD_T)::type_id::create("agent_B", this);
      agent_A_mon_fifo = new("agent_A_mon_fifo", this);
      agent_B_mon_fifo = new("agent_B_mon_fifo", this);
    endfunction

    function void connect_phase(uvm_phase phase);
      super.connect_phase(phase);
      agent_A.ap.connect(agent_A_mon_fifo.analysis_export);
      agent_B.ap.connect(agent_B_mon_fifo.analysis_export);
    endfunction
  endclass

  // ============================
  // Reaction sequence
  // Drives a seed item, then waits to observe it via
  // the cross-interface observe_fifo before sending
  // reaction items.
  // ============================
  class mode08_reaction_seq extends uvm_sequence #(xif_item #(mode08_pd_t));
    rand int unsigned reaction_items;

    `uvm_object_utils(mode08_reaction_seq)

    uvm_tlm_analysis_fifo #(xif_item #(mode08_pd_t)) observe_fifo;

    function new(string name = "mode08_reaction_seq");
      super.new(name);
      reaction_items = 3;
    endfunction

    task body();
      xif_item #(mode08_pd_t) req;
      xif_item #(mode08_pd_t) observed;
      int unsigned idx;

      // Drive seed item
      req = xif_item #(mode08_pd_t)::type_id::create("seed_req");
      req.pd.opcode = 8'h50;
      req.pd.data = 16'h8000;
      req.leading_cycles = 0;
      req.post_cycles = 0;
      `uvm_info("MODE08_SEQ", $sformatf("sending seed item %s", req.convert2string()), UVM_MEDIUM)
      start_item(req);
      finish_item(req);

      // Cross-interface observation guard
      if (observe_fifo == null) begin
        `uvm_fatal("MODE08_REACT_NOFIFO", "mode08_reaction_seq requires observe_fifo")
      end

      // Wait until seed item appears on the other interface's monitor
      do begin
        observe_fifo.get(observed);
      end while (observed.pd.opcode != 8'h50);
      `uvm_info("MODE08_SEQ", $sformatf("observed seed item on other interface: %s", observed.convert2string()), UVM_MEDIUM)

      // Drive reaction items
      for (idx = 0; idx < reaction_items; idx++) begin
        mode08_pd_t payload;
        payload.opcode = 8'h51 + idx[7:0];
        payload.data   = 16'h8100 + idx[15:0];

        req = xif_item #(mode08_pd_t)::type_id::create($sformatf("reaction_req_%0d", idx));
        req.pd = payload;
        req.leading_cycles = 0;
        req.post_cycles = 0;
        `uvm_info("MODE08_SEQ", $sformatf("sending reaction item %s", req.convert2string()), UVM_MEDIUM)
        start_item(req);
        finish_item(req);
      end
    endtask
  endclass

  // ============================
  // Base test with helpers
  // ============================
  class mode08_base_test extends uvm_test;
    `uvm_component_utils(mode08_base_test)

    xif_cfg                           cfg_A;
    xif_cfg                           cfg_B;
    mode08_env #(mode08_pd_t)         env;
    virtual xif_if #(mode08_pd_t)     vif_A;
    virtual xif_if #(mode08_pd_t)     vif_B;

    function new(string name = "mode08_base_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg_A = xif_cfg::type_id::create("cfg_A");
      cfg_B = xif_cfg::type_id::create("cfg_B");
      env = mode08_env #(mode08_pd_t)::type_id::create("env", this);

      if (!uvm_config_db#(virtual xif_if #(mode08_pd_t))::get(this, "", "vif_A", vif_A))
        `uvm_fatal("NOVIF_A", "test requires vif_A")
      if (!uvm_config_db#(virtual xif_if #(mode08_pd_t))::get(this, "", "vif_B", vif_B))
        `uvm_fatal("NOVIF_B", "test requires vif_B")

      uvm_config_db#(xif_cfg)::set(this, "env.agent_A", "cfg", cfg_A);
      uvm_config_db#(xif_cfg)::set(this, "env.agent_B", "cfg", cfg_B);
      uvm_config_db#(virtual xif_if #(mode08_pd_t))::set(this, "env.agent_A", "vif", vif_A);
      uvm_config_db#(virtual xif_if #(mode08_pd_t))::set(this, "env.agent_B", "vif", vif_B);
      vif_A.set_cfg(cfg_A);
      vif_B.set_cfg(cfg_B);
    endfunction

    task automatic wait_reset_release();
      wait (vif_A.rst_n === 1'b1);
      @(posedge vif_A.clk);
    endtask

    task automatic wait_cycles(int unsigned cycles);
      repeat (cycles) @(posedge vif_A.clk);
    endtask

    task automatic wait_for_mon_items(int unsigned count, time timeout = 5000ns);
      int unsigned seen;
      bit timeout_hit;
      fork : wait_mon_fork
        begin
          xif_item #(mode08_pd_t) item;
          for (seen = 0; seen < count; seen++) begin
            env.agent_A_mon_fifo.get(item);
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
      xif_item #(mode08_pd_t) item;
      wait_cycles(settle_cycles);
      if (env.agent_A_mon_fifo.try_get(item)) begin
        `uvm_fatal("EXTRA_MONITEM", $sformatf("Unexpected extra monitor item: %s", item.convert2string()))
      end
    endtask

    task automatic drive_peer_ready(int unsigned stall_cycles);
      wait_reset_release();
      vif_A.bp <= 1'b0;
      vif_A.rdy <= 1'b0;
      wait_cycles(stall_cycles);
      repeat (128) begin
        vif_A.rdy <= 1'b1;
        @(posedge vif_A.clk);
      end
    endtask
  endclass

  // ============================
  // Concrete test — cross-interface reaction
  // ============================
  class mode08_reaction_sequences_test extends mode08_base_test;
    `uvm_component_utils(mode08_reaction_sequences_test)

    function new(string name = "mode08_reaction_sequences_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg_A.active_passive = UVM_ACTIVE;
      cfg_A.role = XIF_ROLE_MASTER;
      cfg_A.flow_ctrl = XIF_FLOW_CTRL_RDY;
      cfg_A.timeout_cycles = 8;

      cfg_B.active_passive = UVM_PASSIVE;
      cfg_B.flow_ctrl = XIF_FLOW_CTRL_RDY;
    endfunction

    task run_phase(uvm_phase phase);
      mode08_reaction_seq seq;

      phase.raise_objection(this);
      fork
        drive_peer_ready(2);
      join_none

      wait_reset_release();
      seq = mode08_reaction_seq::type_id::create("seq");
      seq.observe_fifo = env.agent_B_mon_fifo;
      seq.reaction_items = 3;
      seq.start(env.agent_A.sequencer);

      wait_for_mon_items(4);
      expect_no_extra_mon_items();
      phase.drop_objection(this);
    endtask
  endclass

endpackage

`endif
