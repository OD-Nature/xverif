`ifndef MODE09_INTEGRATED_STRESS_PKG_SV
`define MODE09_INTEGRATED_STRESS_PKG_SV

package mode09_integrated_stress_pkg;
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
  } mode09_pd_t;

  // ============================
  // Environment
  // ============================
  class mode09_env #(type PD_T = mode09_pd_t) extends uvm_env;
    `uvm_component_param_utils(mode09_env #(PD_T))

    xif_agent #(PD_T)                         agent;
    uvm_tlm_analysis_fifo #(xif_item #(PD_T)) mon_fifo;

    function new(string name = "mode09_env", uvm_component parent = null);
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
  // Sub-sequence 1: Back-to-Back
  // ============================
  class mode09_back_to_back_seq extends uvm_sequence #(xif_item #(mode09_pd_t));
    rand int unsigned num_items;
    rand logic [7:0]  opcode_base;
    rand logic [15:0] data_base;

    `uvm_object_utils(mode09_back_to_back_seq)

    function new(string name = "mode09_back_to_back_seq");
      super.new(name);
      num_items = 3;
      opcode_base = 8'h60;
      data_base = 16'h9000;
    endfunction

    task body();
      xif_item #(mode09_pd_t) req;
      int unsigned idx;

      for (idx = 0; idx < num_items; idx++) begin
        mode09_pd_t payload;
        payload.opcode = opcode_base + idx[7:0];
        payload.data   = data_base + idx[15:0];

        req = xif_item #(mode09_pd_t)::type_id::create($sformatf("btb_req_%0d", idx));
        req.pd = payload;
        req.leading_cycles = 0;
        req.post_cycles = 0;

        `uvm_info("MODE09_BTB_SEQ", $sformatf("sending item %s", req.convert2string()), UVM_MEDIUM)
        start_item(req);
        finish_item(req);
      end
    endtask
  endclass

  // ============================
  // Sub-sequence 2: Burst
  // ============================
  class mode09_burst_seq extends uvm_sequence #(xif_item #(mode09_pd_t));
    rand int unsigned num_bursts;
    rand int unsigned burst_len;
    rand int unsigned burst_gap;

    `uvm_object_utils(mode09_burst_seq)

    function new(string name = "mode09_burst_seq");
      super.new(name);
      num_bursts = 2;
      burst_len = 2;
      burst_gap = 1;
    endfunction

    task body();
      xif_item #(mode09_pd_t) req;
      int unsigned burst_idx;
      int unsigned beat_idx;

      for (burst_idx = 0; burst_idx < num_bursts; burst_idx++) begin
        for (beat_idx = 0; beat_idx < burst_len; beat_idx++) begin
          mode09_pd_t payload;
          payload.opcode = 8'h70 + burst_idx[3:0];
          payload.data   = 16'ha000 + (burst_idx * 16) + beat_idx[15:0];

          req = xif_item #(mode09_pd_t)::type_id::create($sformatf("burst_%0d_%0d", burst_idx, beat_idx));
          req.pd = payload;
          req.leading_cycles = ((burst_idx != 0) && (beat_idx == 0)) ? burst_gap : 0;
          req.post_cycles = 0;

          `uvm_info("MODE09_BURST_SEQ", $sformatf("sending item %s", req.convert2string()), UVM_MEDIUM)
          start_item(req);
          finish_item(req);
        end
      end
    endtask
  endclass

  // ============================
  // Sub-sequence 3: Pulse
  // ============================
  class mode09_pulse_seq extends uvm_sequence #(xif_item #(mode09_pd_t));
    rand int unsigned pulses;
    rand int unsigned pulse_width;
    rand int unsigned pulse_period;

    `uvm_object_utils(mode09_pulse_seq)

    function new(string name = "mode09_pulse_seq");
      super.new(name);
      pulses = 2;
      pulse_width = 2;
      pulse_period = 4;
    endfunction

    task body();
      xif_item #(mode09_pd_t) req;
      int unsigned pulse_idx;
      int unsigned beat_idx;
      int unsigned gap;

      gap = (pulse_period > pulse_width) ? (pulse_period - pulse_width) : 0;
      for (pulse_idx = 0; pulse_idx < pulses; pulse_idx++) begin
        for (beat_idx = 0; beat_idx < pulse_width; beat_idx++) begin
          mode09_pd_t payload;
          payload.opcode = 8'h80 + pulse_idx[7:0];
          payload.data   = 16'hb000 + (pulse_idx * 16) + beat_idx[15:0];

          req = xif_item #(mode09_pd_t)::type_id::create($sformatf("pulse_%0d_%0d", pulse_idx, beat_idx));
          req.pd = payload;
          req.leading_cycles = ((pulse_idx != 0) && (beat_idx == 0)) ? gap : 0;
          req.post_cycles = 0;

          `uvm_info("MODE09_PULSE_SEQ", $sformatf("sending item %s", req.convert2string()), UVM_MEDIUM)
          start_item(req);
          finish_item(req);
        end
      end
    endtask
  endclass

  // ============================
  // Sub-sequence 4: Multi-Channel Outstanding
  // ============================
  class mode09_multi_channel_outstanding_seq extends uvm_sequence #(xif_item #(mode09_pd_t));
    rand int unsigned channels;
    rand int unsigned ids_per_channel;
    rand int unsigned max_outstanding;

    `uvm_object_utils(mode09_multi_channel_outstanding_seq)

    function new(string name = "mode09_multi_channel_outstanding_seq");
      super.new(name);
      channels = 4;
      ids_per_channel = 2;
      max_outstanding = 4;
    endfunction

    task body();
      xif_item #(mode09_pd_t) req;
      int unsigned channel_idx;
      int unsigned id_idx;
      int unsigned issued_since_gap;

      issued_since_gap = 0;
      for (id_idx = 0; id_idx < ids_per_channel; id_idx++) begin
        for (channel_idx = 0; channel_idx < channels; channel_idx++) begin
          mode09_pd_t payload;
          payload.opcode = {channel_idx[1:0], id_idx[5:0]};
          payload.data   = 16'h7000 + (channel_idx * 16) + id_idx[15:0];

          req = xif_item #(mode09_pd_t)::type_id::create($sformatf("mc_ch%0d_id%0d", channel_idx, id_idx));
          req.pd = payload;
          req.leading_cycles = 0;
          req.post_cycles = ((max_outstanding != 0) && (issued_since_gap + 1 >= max_outstanding)) ? 1 : 0;

          `uvm_info("MODE09_MC_SEQ", $sformatf("sending item %s", req.convert2string()), UVM_MEDIUM)
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
  // Sub-sequence 5: Reaction
  // ============================
  class mode09_reaction_seq extends uvm_sequence #(xif_item #(mode09_pd_t));
    rand int unsigned reaction_items;

    `uvm_object_utils(mode09_reaction_seq)

    uvm_tlm_analysis_fifo #(xif_item #(mode09_pd_t)) observe_fifo;

    function new(string name = "mode09_reaction_seq");
      super.new(name);
      reaction_items = 2;
    endfunction

    task body();
      xif_item #(mode09_pd_t) req;
      xif_item #(mode09_pd_t) observed;
      int unsigned idx;
      mode09_pd_t payload;

      // Send seed item
      payload.opcode = 8'h90;
      payload.data   = 16'hc000;
      req = xif_item #(mode09_pd_t)::type_id::create("seed_req");
      req.pd = payload;
      req.leading_cycles = 0;
      req.post_cycles = 0;
      start_item(req);
      finish_item(req);

      if (observe_fifo == null) begin
        `uvm_fatal("MODE09_REACT_NOFIFO", "mode09_reaction_seq requires observe_fifo")
      end

      // Wait until seed item is observed on the monitor
      do begin
        observe_fifo.get(observed);
      end while (observed.pd.opcode != 8'h90);

      // Send reaction items
      for (idx = 0; idx < reaction_items; idx++) begin
        payload.opcode = 8'h91 + idx[7:0];
        payload.data   = 16'hc100 + idx[15:0];

        req = xif_item #(mode09_pd_t)::type_id::create($sformatf("reaction_req_%0d", idx));
        req.pd = payload;
        req.leading_cycles = 0;
        req.post_cycles = 0;

        `uvm_info("MODE09_REACT_SEQ", $sformatf("sending reaction item %s", req.convert2string()), UVM_MEDIUM)
        start_item(req);
        finish_item(req);
      end
    endtask
  endclass

  // ============================
  // All-Features Sequence
  // ============================
  class mode09_all_features_seq extends uvm_sequence #(xif_item #(mode09_pd_t));
    `uvm_object_utils(mode09_all_features_seq)

    uvm_tlm_analysis_fifo #(xif_item #(mode09_pd_t)) observe_fifo;

    function new(string name = "mode09_all_features_seq");
      super.new(name);
    endfunction

    task body();
      mode09_back_to_back_seq                  btb_seq;
      mode09_burst_seq                         burst_seq;
      mode09_pulse_seq                         pulse_seq;
      mode09_multi_channel_outstanding_seq     mc_seq;
      mode09_reaction_seq                      reaction_seq;

      // 1. Back-to-back
      btb_seq = mode09_back_to_back_seq::type_id::create("btb_seq");
      btb_seq.num_items = 3;
      btb_seq.opcode_base = 8'h60;
      btb_seq.data_base = 16'h9000;
      btb_seq.start(m_sequencer);

      // 2. Burst
      burst_seq = mode09_burst_seq::type_id::create("burst_seq");
      burst_seq.num_bursts = 2;
      burst_seq.burst_len = 2;
      burst_seq.burst_gap = 1;
      burst_seq.start(m_sequencer);

      // 3. Pulse
      pulse_seq = mode09_pulse_seq::type_id::create("pulse_seq");
      pulse_seq.pulses = 2;
      pulse_seq.pulse_width = 2;
      pulse_seq.pulse_period = 4;
      pulse_seq.start(m_sequencer);

      // 4. Multi-channel outstanding
      mc_seq = mode09_multi_channel_outstanding_seq::type_id::create("mc_seq");
      mc_seq.channels = 4;
      mc_seq.ids_per_channel = 2;
      mc_seq.max_outstanding = 4;
      mc_seq.start(m_sequencer);

      // 5. Reaction (set observe_fifo before start)
      reaction_seq = mode09_reaction_seq::type_id::create("reaction_seq");
      reaction_seq.observe_fifo = observe_fifo;
      reaction_seq.reaction_items = 2;
      reaction_seq.start(m_sequencer);
    endtask
  endclass

  // ============================
  // Base test with helpers
  // ============================
  class mode09_base_test extends uvm_test;
    `uvm_component_utils(mode09_base_test)

    xif_cfg                           cfg;
    mode09_env #(mode09_pd_t)         env;
    virtual xif_if #(mode09_pd_t)     vif;

    function new(string name = "mode09_base_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg = xif_cfg::type_id::create("cfg");
      env = mode09_env #(mode09_pd_t)::type_id::create("env", this);
      if (!uvm_config_db#(virtual xif_if #(mode09_pd_t))::get(this, "", "vif", vif)) begin
        `uvm_fatal("NOVIF", "test requires virtual interface")
      end
      uvm_config_db#(xif_cfg)::set(this, "env*", "cfg", cfg);
      uvm_config_db#(virtual xif_if #(mode09_pd_t))::set(this, "env*", "vif", vif);
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
          xif_item #(mode09_pd_t) item;
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
      xif_item #(mode09_pd_t) item;
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
  class mode09_integrated_stress_test extends mode09_base_test;
    `uvm_component_utils(mode09_integrated_stress_test)

    function new(string name = "mode09_integrated_stress_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg.active_passive = UVM_ACTIVE;
      cfg.role = XIF_ROLE_MASTER;
      cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
      cfg.timeout_cycles = 12;
    endfunction

    task run_phase(uvm_phase phase);
      mode09_all_features_seq seq;

      phase.raise_objection(this);
      fork
        drive_peer_ready(2);
      join_none

      wait_reset_release();
      seq = mode09_all_features_seq::type_id::create("seq");
      seq.observe_fifo = env.mon_fifo;
      seq.start(env.agent.sequencer);

      // The reaction seq uses env.mon_fifo as observe_fifo; its body()
      // drains all pre-seed items + seed from the FIFO, leaving only the
      // 2 reaction items.  Thus we wait for exactly 2 residual items.
      wait_for_mon_items(2);
      expect_no_extra_mon_items();
      phase.drop_objection(this);
    endtask
  endclass

endpackage

`endif
