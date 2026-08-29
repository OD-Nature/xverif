`ifndef XIF_COMPLEX_SEQUENCE_TEST_SVH
`define XIF_COMPLEX_SEQUENCE_TEST_SVH

class xif_back_to_back_sequence_test extends xif_base_test;
  `uvm_component_utils(xif_back_to_back_sequence_test)

  function new(string name = "xif_back_to_back_sequence_test", uvm_component parent = null);
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
    xif_back_to_back_seq seq;

    phase.raise_objection(this);
    fork
      drive_peer_ready(0);
    join_none

    wait_reset_release();
    seq = xif_back_to_back_seq::type_id::create("seq");
    seq.num_items = 4;
    seq.start(env.agent.sequencer);
    wait_for_mon_items(4);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

class xif_burst_sequence_test extends xif_base_test;
  `uvm_component_utils(xif_burst_sequence_test)

  function new(string name = "xif_burst_sequence_test", uvm_component parent = null);
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
    xif_burst_seq seq;

    phase.raise_objection(this);
    fork
      drive_peer_ready(0);
    join_none

    wait_reset_release();
    seq = xif_burst_seq::type_id::create("seq");
    seq.num_bursts = 2;
    seq.burst_len = 3;
    seq.burst_gap = 2;
    seq.start(env.agent.sequencer);
    wait_for_mon_items(6);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

class xif_pulse_sequence_test extends xif_base_test;
  `uvm_component_utils(xif_pulse_sequence_test)

  function new(string name = "xif_pulse_sequence_test", uvm_component parent = null);
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
    xif_pulse_seq seq;

    phase.raise_objection(this);
    fork
      drive_peer_ready(0);
    join_none

    wait_reset_release();
    seq = xif_pulse_seq::type_id::create("seq");
    seq.pulses = 3;
    seq.pulse_width = 2;
    seq.pulse_period = 5;
    seq.start(env.agent.sequencer);
    wait_for_mon_items(6);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

class xif_multi_channel_outstanding_test extends xif_base_test;
  `uvm_component_utils(xif_multi_channel_outstanding_test)

  function new(string name = "xif_multi_channel_outstanding_test", uvm_component parent = null);
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
    xif_multi_channel_outstanding_seq seq;

    phase.raise_objection(this);
    fork
      drive_peer_ready(0);
    join_none

    wait_reset_release();
    seq = xif_multi_channel_outstanding_seq::type_id::create("seq");
    seq.channels = 4;
    seq.ids_per_channel = 2;
    seq.max_outstanding = 4;
    seq.start(env.agent.sequencer);
    wait_for_mon_items(8);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

class xif_multi_channel_weighted_arb_test extends xif_base_test;
  `uvm_component_utils(xif_multi_channel_weighted_arb_test)

  function new(string name = "xif_multi_channel_weighted_arb_test", uvm_component parent = null);
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
    xif_multi_channel_outstanding_seq seq;
    xif_xaction_cfg xaction;
    xif_item #(xif_pd_t) item;
    int unsigned observed_by_id[3];
    int unsigned observed_total;

    phase.raise_objection(this);
    fork
      drive_peer_ready(0);
    join_none

    wait_reset_release();

    xaction = xif_xaction_cfg::type_id::create("xaction");
    xaction.id_count = 3;
    xaction.channels = 2;
    xaction.beats_per_id = 2;
    xaction.enable_weighted_id_select = 1'b1;
    xaction.scheduler_seed = 32'h1;
    xaction.arb_mode = UVM_SEQ_ARB_WEIGHTED;
    xaction.id_weights = new[3];
    xaction.id_weights[0] = 1;
    xaction.id_weights[1] = 3;
    xaction.id_weights[2] = 6;
    xaction.sanitize();

    seq = xif_multi_channel_outstanding_seq::type_id::create("seq");
    seq.xaction = xaction;
    seq.vif = vif;
    seq.start(env.agent.sequencer);

    observed_total = xaction.expected_item_count();
    repeat (observed_total) begin
      env.mon_fifo.get(item);
      if (item.pd.opcode[5:0] < 3) begin
        observed_by_id[item.pd.opcode[5:0]]++;
      end
    end

    if (env.agent.sequencer.get_arbitration() != UVM_SEQ_ARB_WEIGHTED) begin
      `uvm_fatal("ARB_MODE", "xaction did not configure sequencer arbitration mode")
    end

    if ((xaction.start_count_by_id.size() != 3) ||
        (xaction.start_weight_by_id.size() != 3)) begin
      `uvm_fatal("WEIGHT_STATS", "xaction did not record per-ID start_item weight usage")
    end

    if ((xaction.start_weight_by_id[0] != 1) ||
        (xaction.start_weight_by_id[1] != 3) ||
        (xaction.start_weight_by_id[2] != 6)) begin
      `uvm_fatal("WEIGHT_VALUE", "start_item did not use the expected per-ID weights")
    end

    if ((observed_by_id[0] == 0) || (observed_by_id[1] == 0) || (observed_by_id[2] == 0)) begin
      `uvm_fatal("MISSING_ID", $sformatf("observed_by_id=%0d/%0d/%0d", observed_by_id[0], observed_by_id[1], observed_by_id[2]))
    end

    if (!((observed_by_id[2] > observed_by_id[1]) && (observed_by_id[1] > observed_by_id[0]))) begin
      `uvm_fatal("WEIGHT_RATIO", $sformatf("weighted traffic did not follow expected ordering: %0d/%0d/%0d", observed_by_id[0], observed_by_id[1], observed_by_id[2]))
    end

    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

class xif_driver_mailbox_prefetch_test extends xif_base_test;
  `uvm_component_utils(xif_driver_mailbox_prefetch_test)

  function new(string name = "xif_driver_mailbox_prefetch_test", uvm_component parent = null);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    cfg.active_passive = UVM_ACTIVE;
    cfg.role = XIF_ROLE_MASTER;
    cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
    cfg.timeout_cycles = 32;
  endfunction

  task run_phase(uvm_phase phase);
    xif_back_to_back_seq seq;
    bit seq_done;

    phase.raise_objection(this);
    wait_reset_release();
    vif.bp <= 1'b0;
    vif.rdy <= 1'b0;

    seq = xif_back_to_back_seq::type_id::create("seq");
    seq.num_items = 2;
    fork
      begin
        seq.start(env.agent.sequencer);
        seq_done = 1'b1;
      end
    join_none

    wait_cycles(4);
    if (!seq_done) begin
      `uvm_fatal("SEQ_NOT_PREFETCHED", "sequence did not complete while the first bus item was still blocked")
    end

    vif.rdy <= 1'b1;
    wait_for_mon_items(2);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

class xif_reaction_sequence_test extends xif_base_test;
  `uvm_component_utils(xif_reaction_sequence_test)

  function new(string name = "xif_reaction_sequence_test", uvm_component parent = null);
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
    xif_reaction_seq seq;

    phase.raise_objection(this);
    fork
      drive_peer_ready(0);
    join_none

    wait_reset_release();
    seq = xif_reaction_seq::type_id::create("seq");
    seq.observe_fifo = env.mon_fifo;
    seq.reaction_items = 3;
    seq.start(env.agent.sequencer);
    wait_for_mon_items(3);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

class xif_complex_integrated_test extends xif_base_test;
  `uvm_component_utils(xif_complex_integrated_test)

  function new(string name = "xif_complex_integrated_test", uvm_component parent = null);
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
    xif_all_features_seq seq;

    phase.raise_objection(this);
    fork
      drive_peer_ready(0);
    join_none

    wait_reset_release();
    seq = xif_all_features_seq::type_id::create("seq");
    seq.observe_fifo = env.mon_fifo;
    seq.start(env.agent.sequencer);
    wait_for_mon_items(2);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

`endif
