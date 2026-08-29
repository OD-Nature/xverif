`ifndef MODE10_MASTER_SLAVE_AGENT_PAIRING_PKG_SV
`define MODE10_MASTER_SLAVE_AGENT_PAIRING_PKG_SV

package mode10_master_slave_agent_pairing_pkg;
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
  } mode10_pd_t;

  // ============================
  // Dual agent environment
  // ============================
  class mode10_dual_env #(type PD_T = mode10_pd_t) extends uvm_env;
    `uvm_component_param_utils(mode10_dual_env #(PD_T))

    xif_agent #(PD_T)                         master_agent;
    xif_agent #(PD_T)                         slave_agent;
    uvm_tlm_analysis_fifo #(xif_item #(PD_T)) master_mon_fifo;
    uvm_tlm_analysis_fifo #(xif_item #(PD_T)) slave_mon_fifo;

    function new(string name = "mode10_dual_env", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      master_agent = xif_agent #(PD_T)::type_id::create("master_agent", this);
      slave_agent  = xif_agent #(PD_T)::type_id::create("slave_agent", this);
      master_mon_fifo = new("master_mon_fifo", this);
      slave_mon_fifo  = new("slave_mon_fifo", this);
    endfunction

    function void connect_phase(uvm_phase phase);
      super.connect_phase(phase);
      master_agent.ap.connect(master_mon_fifo.analysis_export);
      slave_agent.ap.connect(slave_mon_fifo.analysis_export);
    endfunction
  endclass

  // ============================
  // Simplified multi-channel outstanding sequence (legacy mode)
  // ============================
  class mode10_multi_channel_outstanding_seq extends uvm_sequence #(xif_item #(mode10_pd_t));
    rand int unsigned channels;
    rand int unsigned ids_per_channel;
    rand int unsigned max_outstanding;

    `uvm_object_utils(mode10_multi_channel_outstanding_seq)

    function new(string name = "mode10_multi_channel_outstanding_seq");
      super.new(name);
      channels        = 4;
      ids_per_channel = 2;
      max_outstanding = 4;
    endfunction

    task body();
      xif_item #(mode10_pd_t) req;
      int unsigned channel_idx;
      int unsigned id_idx;
      int unsigned issued_since_gap;

      issued_since_gap = 0;
      for (id_idx = 0; id_idx < ids_per_channel; id_idx++) begin
        for (channel_idx = 0; channel_idx < channels; channel_idx++) begin
          mode10_pd_t payload;
          payload.opcode = {channel_idx[1:0], id_idx[5:0]};
          payload.data   = 16'h7000 + (channel_idx * 16) + id_idx;

          req = xif_item #(mode10_pd_t)::type_id::create($sformatf("mc_ch%0d_id%0d", channel_idx, id_idx));
          req.pd = payload;
          req.leading_cycles = 0;
          req.post_cycles = ((max_outstanding != 0) && (issued_since_gap + 1 >= max_outstanding)) ? 1 : 0;

          `uvm_info("MODE10_SEQ", $sformatf("sending item %s", req.convert2string()), UVM_MEDIUM)
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
  // Standalone test (NOT base_test)
  // ============================
  class mode10_master_slave_agent_pairing_test extends uvm_test;
    `uvm_component_utils(mode10_master_slave_agent_pairing_test)

    xif_cfg                                  master_agent_cfg;
    xif_cfg                                  slave_agent_cfg;
    mode10_dual_env #(mode10_pd_t)           env;
    virtual xif_if #(mode10_pd_t)            master_vif;
    virtual xif_if #(mode10_pd_t)            slave_vif;

    function new(string name = "mode10_master_slave_agent_pairing_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);

      master_agent_cfg = xif_cfg::type_id::create("master_agent_cfg");
      master_agent_cfg.active_passive = UVM_ACTIVE;
      master_agent_cfg.role = XIF_ROLE_MASTER;
      master_agent_cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
      master_agent_cfg.timeout_cycles = 12;

      slave_agent_cfg = xif_cfg::type_id::create("slave_agent_cfg");
      slave_agent_cfg.active_passive = UVM_ACTIVE;
      slave_agent_cfg.role = XIF_ROLE_SLAVE_RESPONDER;
      slave_agent_cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
      slave_agent_cfg.responder_mode = XIF_RESP_PULSE;
      slave_agent_cfg.pulse_period_cycles = 4;
      slave_agent_cfg.pulse_width_cycles = 1;
      slave_agent_cfg.timeout_cycles = 12;

      env = mode10_dual_env #(mode10_pd_t)::type_id::create("env", this);

      if (!uvm_config_db#(virtual xif_if #(mode10_pd_t))::get(this, "", "master_vif", master_vif)) begin
        `uvm_fatal("NOMASTERIF", "dual test requires master_vif")
      end
      if (!uvm_config_db#(virtual xif_if #(mode10_pd_t))::get(this, "", "slave_vif", slave_vif)) begin
        `uvm_fatal("NOSLAVEIF", "dual test requires slave_vif")
      end

      uvm_config_db#(virtual xif_if #(mode10_pd_t))::set(this, "env.master_agent", "vif", master_vif);
      uvm_config_db#(virtual xif_if #(mode10_pd_t))::set(this, "env.slave_agent",  "vif", slave_vif);
      uvm_config_db#(xif_cfg)::set(this, "env.master_agent", "cfg", master_agent_cfg);
      uvm_config_db#(xif_cfg)::set(this, "env.slave_agent",  "cfg", slave_agent_cfg);

      master_vif.set_cfg(master_agent_cfg);
      slave_vif.set_cfg(slave_agent_cfg);
    endfunction

    task run_phase(uvm_phase phase);
      mode10_multi_channel_outstanding_seq seq;
      xif_item #(mode10_pd_t) item;
      int unsigned idx;

      phase.raise_objection(this);

      wait (master_vif.rst_n === 1'b1);
      @(posedge master_vif.clk);

      seq = mode10_multi_channel_outstanding_seq::type_id::create("seq");
      seq.channels = 4;
      seq.ids_per_channel = 2;
      seq.max_outstanding = 4;
      seq.start(env.master_agent.sequencer);

      for (idx = 0; idx < 8; idx++) begin
        env.master_mon_fifo.get(item);
        `uvm_info("MODE10_MON", item.convert2string(), UVM_MEDIUM)
      end

      repeat (4) @(posedge master_vif.clk);

      if (env.master_mon_fifo.try_get(item)) begin
        `uvm_fatal("EXTRA_MONITEM", $sformatf("Unexpected extra monitor item: %s", item.convert2string()))
      end

      phase.drop_objection(this);
    endtask
  endclass

endpackage

`endif
