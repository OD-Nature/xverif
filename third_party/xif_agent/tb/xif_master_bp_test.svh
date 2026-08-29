`ifndef XIF_MASTER_BP_TEST_SVH
`define XIF_MASTER_BP_TEST_SVH

class xif_master_bp_test extends xif_base_test;
  `uvm_component_utils(xif_master_bp_test)

  function new(string name = "xif_master_bp_test", uvm_component parent = null);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    cfg.active_passive = UVM_ACTIVE;
    cfg.role = XIF_ROLE_MASTER;
    cfg.flow_ctrl = XIF_FLOW_CTRL_BP;
    cfg.timeout_cycles = 10;
    cfg.idle_pd_policy = XIF_IDLE_X_ONLY;
  endfunction

  task run_phase(uvm_phase phase);
    phase.raise_objection(this);
    fork
      drive_peer_bp(3);
    join_none

    start_master_sequence(3);
    wait_for_mon_items(3);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

`endif
