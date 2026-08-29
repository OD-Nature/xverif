`ifndef XIF_COMPLEX_SEQ_SVH
`define XIF_COMPLEX_SEQ_SVH

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

class xif_back_to_back_seq extends uvm_sequence #(xif_item #(xif_pd_t));
  rand int unsigned num_items;
  rand logic [7:0]  opcode_base;
  rand logic [15:0] data_base;

  `uvm_object_utils(xif_back_to_back_seq)

  function new(string name = "xif_back_to_back_seq");
    super.new(name);
    num_items = 4;
    opcode_base = 8'h20;
    data_base = 16'h4000;
  endfunction

  task body();
    xif_item #(xif_pd_t) req;
    int unsigned idx;

    for (idx = 0; idx < num_items; idx++) begin
      req = xif_item #(xif_pd_t)::type_id::create($sformatf("btb_req_%0d", idx));
      req.pd.opcode = opcode_base + idx[7:0];
      req.pd.data = data_base + idx[15:0];
      req.leading_cycles = 0;
      req.post_cycles = 0;
      start_item(req);
      finish_item(req);
    end
  endtask
endclass

class xif_burst_seq extends uvm_sequence #(xif_item #(xif_pd_t));
  rand int unsigned num_bursts;
  rand int unsigned burst_len;
  rand int unsigned burst_gap;

  `uvm_object_utils(xif_burst_seq)

  function new(string name = "xif_burst_seq");
    super.new(name);
    num_bursts = 2;
    burst_len = 3;
    burst_gap = 2;
  endfunction

  task body();
    xif_item #(xif_pd_t) req;
    int unsigned burst_idx;
    int unsigned beat_idx;

    for (burst_idx = 0; burst_idx < num_bursts; burst_idx++) begin
      for (beat_idx = 0; beat_idx < burst_len; beat_idx++) begin
        req = xif_item #(xif_pd_t)::type_id::create($sformatf("burst_%0d_%0d", burst_idx, beat_idx));
        req.pd.opcode = 8'h30 + burst_idx[3:0];
        req.pd.data = 16'h5000 + (burst_idx * 16) + beat_idx;
        req.leading_cycles = ((burst_idx != 0) && (beat_idx == 0)) ? burst_gap : 0;
        req.post_cycles = 0;
        start_item(req);
        finish_item(req);
      end
    end
  endtask
endclass

class xif_pulse_seq extends uvm_sequence #(xif_item #(xif_pd_t));
  rand int unsigned pulses;
  rand int unsigned pulse_width;
  rand int unsigned pulse_period;

  `uvm_object_utils(xif_pulse_seq)

  function new(string name = "xif_pulse_seq");
    super.new(name);
    pulses = 3;
    pulse_width = 2;
    pulse_period = 5;
  endfunction

  task body();
    xif_item #(xif_pd_t) req;
    int unsigned pulse_idx;
    int unsigned beat_idx;
    int unsigned gap;

    gap = (pulse_period > pulse_width) ? (pulse_period - pulse_width) : 0;
    for (pulse_idx = 0; pulse_idx < pulses; pulse_idx++) begin
      for (beat_idx = 0; beat_idx < pulse_width; beat_idx++) begin
        req = xif_item #(xif_pd_t)::type_id::create($sformatf("pulse_%0d_%0d", pulse_idx, beat_idx));
        req.pd.opcode = 8'h40 + pulse_idx[7:0];
        req.pd.data = 16'h6000 + (pulse_idx * 16) + beat_idx;
        req.leading_cycles = ((pulse_idx != 0) && (beat_idx == 0)) ? gap : 0;
        req.post_cycles = 0;
        start_item(req);
        finish_item(req);
      end
    end
  endtask
endclass

class xif_multi_channel_outstanding_seq extends uvm_sequence #(xif_item #(xif_pd_t));
  rand int unsigned channels;
  rand int unsigned ids_per_channel;
  rand int unsigned max_outstanding;
  xif_xaction_cfg xaction;
  virtual xif_if #(xif_pd_t) vif;

  local semaphore send_sem;
  local mailbox id_tokens[];

  `uvm_object_utils(xif_multi_channel_outstanding_seq)

  function new(string name = "xif_multi_channel_outstanding_seq");
    super.new(name);
    channels = 4;
    ids_per_channel = 2;
    max_outstanding = 4;
    send_sem = new(1);
  endfunction

  task automatic send_one_item(int unsigned channel_idx, int unsigned id, int unsigned beat_idx);
    xif_item #(xif_pd_t) req;

    req = xif_item #(xif_pd_t)::type_id::create($sformatf("mc_ch%0d_id%0d_beat%0d", channel_idx, id, beat_idx));
    req.pd.opcode = {channel_idx[1:0], id[5:0]};
    req.pd.data = 16'h7000 + (channel_idx * 16) + beat_idx;
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
    int token;

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

  task automatic run_legacy_body();
    xif_item #(xif_pd_t) req;
    int unsigned channel_idx;
    int unsigned id_idx;
    int unsigned issued_since_gap;

    issued_since_gap = 0;
    for (id_idx = 0; id_idx < ids_per_channel; id_idx++) begin
      for (channel_idx = 0; channel_idx < channels; channel_idx++) begin
        req = xif_item #(xif_pd_t)::type_id::create($sformatf("mc_ch%0d_id%0d", channel_idx, id_idx));
        req.pd.opcode = {channel_idx[1:0], id_idx[5:0]};
        req.pd.data = 16'h7000 + (channel_idx * 16) + id_idx;
        req.leading_cycles = 0;
        req.post_cycles = ((max_outstanding != 0) && (issued_since_gap + 1 >= max_outstanding)) ? 1 : 0;
        start_item(req);
        finish_item(req);
        issued_since_gap++;
        if ((max_outstanding != 0) && (issued_since_gap >= max_outstanding)) begin
          issued_since_gap = 0;
        end
      end
    end
  endtask

  task body();
    if (xaction != null) begin
      run_xaction_body();
    end else begin
      run_legacy_body();
    end
  endtask
endclass

class xif_reaction_seq extends uvm_sequence #(xif_item #(xif_pd_t));
  rand int unsigned reaction_items;

  `uvm_object_utils(xif_reaction_seq)

  uvm_tlm_analysis_fifo #(xif_item #(xif_pd_t)) observe_fifo;

  function new(string name = "xif_reaction_seq");
    super.new(name);
    reaction_items = 3;
  endfunction

  task body();
    xif_item #(xif_pd_t) req;
    xif_item #(xif_pd_t) observed;
    int unsigned idx;

    req = xif_item #(xif_pd_t)::type_id::create("seed_req");
    req.pd.opcode = 8'h50;
    req.pd.data = 16'h8000;
    req.leading_cycles = 0;
    req.post_cycles = 0;
    start_item(req);
    finish_item(req);

    if (observe_fifo == null) begin
      `uvm_fatal("XIF_REACT_NOFIFO", "xif_reaction_seq requires observe_fifo")
    end

    do begin
      observe_fifo.get(observed);
    end while (observed.pd.opcode != 8'h50);

    for (idx = 0; idx < reaction_items; idx++) begin
      req = xif_item #(xif_pd_t)::type_id::create($sformatf("reaction_req_%0d", idx));
      req.pd.opcode = 8'h51 + idx[7:0];
      req.pd.data = 16'h8100 + idx[15:0];
      req.leading_cycles = 0;
      req.post_cycles = 0;
      start_item(req);
      finish_item(req);
    end
  endtask
endclass

class xif_all_features_seq extends uvm_sequence #(xif_item #(xif_pd_t));
  `uvm_object_utils(xif_all_features_seq)

  uvm_tlm_analysis_fifo #(xif_item #(xif_pd_t)) observe_fifo;

  function new(string name = "xif_all_features_seq");
    super.new(name);
  endfunction

  task body();
    xif_back_to_back_seq btb_seq;
    xif_burst_seq burst_seq;
    xif_pulse_seq pulse_seq;
    xif_multi_channel_outstanding_seq mc_seq;
    xif_reaction_seq reaction_seq;

    btb_seq = xif_back_to_back_seq::type_id::create("btb_seq");
    btb_seq.num_items = 3;
    btb_seq.opcode_base = 8'h60;
    btb_seq.data_base = 16'h9000;
    btb_seq.start(m_sequencer);

    burst_seq = xif_burst_seq::type_id::create("burst_seq");
    burst_seq.num_bursts = 2;
    burst_seq.burst_len = 2;
    burst_seq.burst_gap = 1;
    burst_seq.start(m_sequencer);

    pulse_seq = xif_pulse_seq::type_id::create("pulse_seq");
    pulse_seq.pulses = 2;
    pulse_seq.pulse_width = 2;
    pulse_seq.pulse_period = 4;
    pulse_seq.start(m_sequencer);

    mc_seq = xif_multi_channel_outstanding_seq::type_id::create("mc_seq");
    mc_seq.channels = 4;
    mc_seq.ids_per_channel = 2;
    mc_seq.max_outstanding = 4;
    mc_seq.start(m_sequencer);

    reaction_seq = xif_reaction_seq::type_id::create("reaction_seq");
    reaction_seq.observe_fifo = observe_fifo;
    reaction_seq.reaction_items = 2;
    reaction_seq.start(m_sequencer);
  endtask
endclass

`endif
