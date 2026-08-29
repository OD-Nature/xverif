`ifndef MODE06_MULTI_CHANNEL_OUTSTANDING_PKG_SV
`define MODE06_MULTI_CHANNEL_OUTSTANDING_PKG_SV

package mode06_multi_channel_outstanding_pkg;
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
  } mode06_pd_t;

  // ============================
  // Environment
  // ============================
  class mode06_env #(type PD_T = mode06_pd_t) extends uvm_env;
    `uvm_component_param_utils(mode06_env #(PD_T))

    xif_agent #(PD_T)                         agent;
    uvm_tlm_analysis_fifo #(xif_item #(PD_T)) mon_fifo;

    function new(string name = "mode06_env", uvm_component parent = null);
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
  // Multi-channel outstanding sequence (legacy mode)
  // ============================
  class mode06_multi_channel_outstanding_seq extends uvm_sequence #(xif_item #(mode06_pd_t));
    rand int unsigned channels;
    rand int unsigned ids_per_channel;
    rand int unsigned max_outstanding;

    `uvm_object_utils(mode06_multi_channel_outstanding_seq)

    function new(string name = "mode06_multi_channel_outstanding_seq");
      super.new(name);
      channels = 4;
      ids_per_channel = 2;
      max_outstanding = 4;
    endfunction

    task body();
      xif_item #(mode06_pd_t) req;
      int unsigned channel_idx;
      int unsigned id_idx;
      int unsigned issued_since_gap;

      issued_since_gap = 0;
      for (id_idx = 0; id_idx < ids_per_channel; id_idx++) begin
        for (channel_idx = 0; channel_idx < channels; channel_idx++) begin
          mode06_pd_t payload;
          payload.opcode = {channel_idx[1:0], id_idx[5:0]};
          payload.data   = 16'h7000 + (channel_idx * 16) + id_idx;

          req = xif_item #(mode06_pd_t)::type_id::create($sformatf("mc_ch%0d_id%0d", channel_idx, id_idx));
          req.pd = payload;
          req.leading_cycles = 0;
          req.post_cycles = ((max_outstanding != 0) && (issued_since_gap + 1 >= max_outstanding)) ? 1 : 0;

          `uvm_info("MODE06_SEQ", $sformatf("sending item %s", req.convert2string()), UVM_MEDIUM)
          start_item(req);
          finish_item(req);
          issued_since_gap++;
          if ((max_outstanding != 0) && (issued_since_gap >= max_outstanding)) begin
            issued_since_gap = 0;
          end
        end
      end
    endtask
  endclass

  // ============================
  // Base test with helpers
  // ============================
  class mode06_base_test extends uvm_test;
    `uvm_component_utils(mode06_base_test)

    xif_cfg                           cfg;
    mode06_env #(mode06_pd_t)         env;
    virtual xif_if #(mode06_pd_t)     vif;

    function new(string name = "mode06_base_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg = xif_cfg::type_id::create("cfg");
      env = mode06_env #(mode06_pd_t)::type_id::create("env", this);
      if (!uvm_config_db#(virtual xif_if #(mode06_pd_t))::get(this, "", "vif", vif)) begin
        `uvm_fatal("NOVIF", "test requires virtual interface")
      end
      uvm_config_db#(xif_cfg)::set(this, "env*", "cfg", cfg);
      uvm_config_db#(virtual xif_if #(mode06_pd_t))::set(this, "env*", "vif", vif);
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
          xif_item #(mode06_pd_t) item;
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
      xif_item #(mode06_pd_t) item;
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
  class mode06_multi_channel_outstanding_test extends mode06_base_test;
    `uvm_component_utils(mode06_multi_channel_outstanding_test)

    function new(string name = "mode06_multi_channel_outstanding_test", uvm_component parent = null);
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
      mode06_multi_channel_outstanding_seq seq;

      phase.raise_objection(this);
      fork
        drive_peer_ready(2);
      join_none

      wait_reset_release();
      seq = mode06_multi_channel_outstanding_seq::type_id::create("seq");
      seq.channels = 4;
      seq.ids_per_channel = 2;
      seq.max_outstanding = 4;
      seq.start(env.agent.sequencer);

      wait_for_mon_items(8);
      expect_no_extra_mon_items();
      phase.drop_objection(this);
    endtask
  endclass

endpackage

`endif
