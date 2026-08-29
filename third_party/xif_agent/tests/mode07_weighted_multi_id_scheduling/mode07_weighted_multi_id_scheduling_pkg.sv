`ifndef MODE07_WEIGHTED_MULTI_ID_SCHEDULING_PKG_SV
`define MODE07_WEIGHTED_MULTI_ID_SCHEDULING_PKG_SV

package mode07_weighted_multi_id_scheduling_pkg;
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
  } mode07_pd_t;

  // ============================
  // xif_xaction_cfg class
  // ============================
  class xif_xaction_cfg extends uvm_object;
    UVM_SEQ_ARB_TYPE arb_mode;
    int unsigned     id_weights[];
    int unsigned     beats_per_id;
    int unsigned     channels;
    int unsigned     id_count;
    bit              enable_seq_lock;
    int unsigned     lock_gap_min_cycles;
    int unsigned     lock_gap_max_cycles;
    int unsigned     lock_hold_min_cycles;
    int unsigned     lock_hold_max_cycles;
    int unsigned     lock_iterations;
    bit              enable_weighted_id_select;
    int unsigned     scheduler_seed;
    int unsigned     start_count_by_id[];
    int unsigned     start_weight_by_id[];

    `uvm_object_utils(xif_xaction_cfg)

    function new(string name = "xif_xaction_cfg");
      super.new(name);
      arb_mode = UVM_SEQ_ARB_WEIGHTED;
      beats_per_id = 1;
      channels = 1;
      id_count = 1;
      enable_seq_lock = 1'b0;
      lock_gap_min_cycles = 1;
      lock_gap_max_cycles = 1;
      lock_hold_min_cycles = 1;
      lock_hold_max_cycles = 1;
      lock_iterations = 0;
      enable_weighted_id_select = 1'b0;
      scheduler_seed = 32'h1;
    endfunction

    function void sanitize();
      int unsigned idx;

      if (id_count == 0) begin
        id_count = 1;
      end
      if (channels == 0) begin
        channels = 1;
      end
      if (beats_per_id == 0) begin
        beats_per_id = 1;
      end
      if (id_weights.size() < id_count) begin
        int unsigned old_size;
        old_size = id_weights.size();
        id_weights = new[id_count](id_weights);
        for (idx = old_size; idx < id_count; idx++) begin
          id_weights[idx] = 1;
        end
      end
      for (idx = 0; idx < id_count; idx++) begin
        if (id_weights[idx] == 0) begin
          id_weights[idx] = 1;
        end
      end
      if (lock_gap_max_cycles < lock_gap_min_cycles) begin
        lock_gap_max_cycles = lock_gap_min_cycles;
      end
      if (lock_hold_max_cycles < lock_hold_min_cycles) begin
        lock_hold_max_cycles = lock_hold_min_cycles;
      end
      start_count_by_id = new[id_count];
      start_weight_by_id = new[id_count];
    endfunction

    function int unsigned id_weight(int unsigned id);
      if ((id < id_weights.size()) && (id_weights[id] != 0)) begin
        return id_weights[id];
      end
      return 1;
    endfunction

    function int unsigned expected_items_for_id(int unsigned id);
      int unsigned multiplier;
      multiplier = enable_weighted_id_select ? id_weight(id) : 1;
      return channels * beats_per_id * multiplier;
    endfunction

    function int unsigned expected_item_count();
      int unsigned total;
      int unsigned id;

      total = 0;
      for (id = 0; id < id_count; id++) begin
        total += expected_items_for_id(id);
      end
      return total;
    endfunction
  endclass

  // ============================
  // Environment
  // ============================
  class mode07_env #(type PD_T = mode07_pd_t) extends uvm_env;
    `uvm_component_param_utils(mode07_env #(PD_T))

    xif_agent #(PD_T)                         agent;
    uvm_tlm_analysis_fifo #(xif_item #(PD_T)) mon_fifo;

    function new(string name = "mode07_env", uvm_component parent = null);
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
  // Multi-channel outstanding sequence (xaction mode)
  // ============================
  class mode07_multi_channel_outstanding_seq extends uvm_sequence #(xif_item #(mode07_pd_t));
    xif_xaction_cfg               xaction;
    virtual xif_if #(mode07_pd_t) vif;

    local semaphore send_sem;
    local mailbox   id_tokens[];

    `uvm_object_utils(mode07_multi_channel_outstanding_seq)

    function new(string name = "mode07_multi_channel_outstanding_seq");
      super.new(name);
      send_sem = new(1);
    endfunction

    task automatic send_one_item(int unsigned channel_idx, int unsigned id, int unsigned beat_idx);
      xif_item #(mode07_pd_t) req;
      mode07_pd_t             payload;

      payload.opcode = {channel_idx[1:0], id[5:0]};
      payload.data   = 16'h7000 + (channel_idx * 16) + beat_idx;

      req = xif_item #(mode07_pd_t)::type_id::create($sformatf("mc_ch%0d_id%0d_beat%0d", channel_idx, id, beat_idx));
      req.pd = payload;
      req.leading_cycles = 0;
      req.post_cycles = 0;
      send_sem.get();
      start_item(req, xaction.id_weight(id));
      finish_item(req);
      send_sem.put();
      xaction.start_count_by_id[id]++;
      xaction.start_weight_by_id[id] = xaction.id_weight(id);
    endtask

    task automatic send_id_traffic(int unsigned id);
      int unsigned channel_idx;
      int unsigned beat_idx;
      int unsigned token;
      int unsigned target_items;
      int unsigned sent_items;

      target_items = xaction.expected_items_for_id(id);
      sent_items = 0;
      while (sent_items < target_items) begin
        id_tokens[id].get(token);
        channel_idx = sent_items % xaction.channels;
        beat_idx = sent_items / xaction.channels;
        send_one_item(channel_idx, id, beat_idx);
        sent_items++;
      end
    endtask

    function automatic int unsigned pick_weighted_id(ref int unsigned remaining_by_id[], ref int unsigned seed);
      int unsigned id;
      int unsigned total_weight;
      int unsigned pick;
      int unsigned cumulative;

      total_weight = 0;
      for (id = 0; id < xaction.id_count; id++) begin
        if (remaining_by_id[id] != 0) begin
          total_weight += xaction.id_weight(id);
        end
      end

      if (total_weight == 0) begin
        return xaction.id_count;
      end

      pick = $urandom(seed) % total_weight;
      cumulative = 0;
      for (id = 0; id < xaction.id_count; id++) begin
        if (remaining_by_id[id] != 0) begin
          cumulative += xaction.id_weight(id);
          if (pick < cumulative) begin
            return id;
          end
        end
      end

      return xaction.id_count - 1;
    endfunction

    task automatic weighted_id_scheduler();
      int unsigned remaining_by_id[];
      int unsigned seed;
      int unsigned id;
      int unsigned idx;
      int          token;

      remaining_by_id = new[xaction.id_count];
      for (id = 0; id < xaction.id_count; id++) begin
        remaining_by_id[id] = xaction.expected_items_for_id(id);
      end

      seed = xaction.scheduler_seed;
      for (idx = 0; idx < xaction.expected_item_count(); idx++) begin
        id = pick_weighted_id(remaining_by_id, seed);
        if (id >= xaction.id_count) begin
          break;
        end
        token = idx;
        id_tokens[id].put(token);
        remaining_by_id[id]--;
      end
    endtask

    task automatic random_lock_control();
      int unsigned idx;
      int unsigned gap_cycles;
      int unsigned hold_cycles;

      if (!xaction.enable_seq_lock || (vif == null)) begin
        return;
      end

      for (idx = 0; idx < xaction.lock_iterations; idx++) begin
        gap_cycles = $urandom_range(xaction.lock_gap_max_cycles, xaction.lock_gap_min_cycles);
        repeat (gap_cycles) @(posedge vif.clk);
        lock(m_sequencer);
        hold_cycles = $urandom_range(xaction.lock_hold_max_cycles, xaction.lock_hold_min_cycles);
        repeat (hold_cycles) @(posedge vif.clk);
        unlock(m_sequencer);
      end
    endtask

    task automatic run_xaction_body();
      int unsigned id;

      xaction.sanitize();
      m_sequencer.set_arbitration(xaction.arb_mode);
      id_tokens = new[xaction.id_count];
      for (id = 0; id < xaction.id_count; id++) begin
        id_tokens[id] = new();
      end

      fork
        weighted_id_scheduler();
        random_lock_control();
        for (id = 0; id < xaction.id_count; id++) begin
          automatic int unsigned task_id = id;
          fork
            send_id_traffic(task_id);
          join_none
        end
      join
      while (started_item_count() < xaction.expected_item_count()) begin
        if (vif != null) begin
          @(posedge vif.clk);
        end else begin
          #1ns;
        end
      end
    endtask

    function int unsigned started_item_count();
      int unsigned total;
      int unsigned id;

      total = 0;
      for (id = 0; id < xaction.start_count_by_id.size(); id++) begin
        total += xaction.start_count_by_id[id];
      end
      return total;
    endfunction

    task body();
      if (xaction != null) begin
        run_xaction_body();
      end
    endtask
  endclass

  // ============================
  // Base test with helpers
  // ============================
  class mode07_base_test extends uvm_test;
    `uvm_component_utils(mode07_base_test)

    xif_cfg                           cfg;
    mode07_env #(mode07_pd_t)         env;
    virtual xif_if #(mode07_pd_t)     vif;

    function new(string name = "mode07_base_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg = xif_cfg::type_id::create("cfg");
      env = mode07_env #(mode07_pd_t)::type_id::create("env", this);
      if (!uvm_config_db#(virtual xif_if #(mode07_pd_t))::get(this, "", "vif", vif)) begin
        `uvm_fatal("NOVIF", "test requires virtual interface")
      end
      uvm_config_db#(xif_cfg)::set(this, "env*", "cfg", cfg);
      uvm_config_db#(virtual xif_if #(mode07_pd_t))::set(this, "env*", "vif", vif);
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
      bit          timeout_hit;
      fork : wait_mon_fork
        begin
          xif_item #(mode07_pd_t) item;
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
      xif_item #(mode07_pd_t) item;
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
  // Concrete test: weighted multi-ID scheduling
  // ============================
  class mode07_weighted_multi_id_scheduling_test extends mode07_base_test;
    `uvm_component_utils(mode07_weighted_multi_id_scheduling_test)

    function new(string name = "mode07_weighted_multi_id_scheduling_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg.active_passive = UVM_ACTIVE;
      cfg.role = XIF_ROLE_MASTER;
      cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
      cfg.timeout_cycles = 16;
    endfunction

    task run_phase(uvm_phase phase);
      xif_xaction_cfg                       xaction_cfg;
      mode07_multi_channel_outstanding_seq  seq;

      phase.raise_objection(this);
      fork
        drive_peer_ready(2);
      join_none

      wait_reset_release();

      xaction_cfg = xif_xaction_cfg::type_id::create("xaction_cfg");
      xaction_cfg.id_count = 3;
      xaction_cfg.channels = 2;
      xaction_cfg.beats_per_id = 2;
      xaction_cfg.enable_weighted_id_select = 1;
      xaction_cfg.id_weights = '{1, 3, 6};
      xaction_cfg.scheduler_seed = 32'h1;
      xaction_cfg.arb_mode = UVM_SEQ_ARB_WEIGHTED;
      xaction_cfg.enable_seq_lock = 1;
      xaction_cfg.lock_gap_min_cycles = 2;
      xaction_cfg.lock_gap_max_cycles = 4;
      xaction_cfg.lock_hold_min_cycles = 2;
      xaction_cfg.lock_hold_max_cycles = 4;
      xaction_cfg.lock_iterations = 3;

      seq = mode07_multi_channel_outstanding_seq::type_id::create("seq");
      seq.xaction = xaction_cfg;
      seq.vif = vif;
      seq.start(env.agent.sequencer);

      wait_for_mon_items(xaction_cfg.expected_item_count());
      expect_no_extra_mon_items();
      phase.drop_objection(this);
    endtask
  endclass

endpackage

`endif
