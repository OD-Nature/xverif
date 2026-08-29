`ifndef XIF_PASSIVE_MONITOR_TEST_SVH
`define XIF_PASSIVE_MONITOR_TEST_SVH

class xif_passive_monitor_test extends xif_base_test;
  `uvm_component_utils(xif_passive_monitor_test)

  function new(string name = "xif_passive_monitor_test", uvm_component parent = null);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    cfg.active_passive = UVM_PASSIVE;
    cfg.role = XIF_ROLE_MASTER;
    cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
    cfg.timeout_cycles = 8;
    cfg.idle_pd_policy = XIF_IDLE_STABLE;
  endfunction

  task run_phase(uvm_phase phase);
    phase.raise_objection(this);

    if ((env.agent.driver != null) || (env.agent.sequencer != null)) begin
      `uvm_fatal("PASSIVE_ACTIVE_COMPONENT", "Passive xif_agent unexpectedly created driver/sequencer")
    end

    fork
      drive_passive_side_items(3);
    join_none

    wait_for_mon_items(3);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

`endif
