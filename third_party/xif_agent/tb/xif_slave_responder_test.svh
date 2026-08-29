`ifndef XIF_SLAVE_RESPONDER_TEST_SVH
`define XIF_SLAVE_RESPONDER_TEST_SVH

class xif_slave_responder_test extends xif_base_test;
  `uvm_component_utils(xif_slave_responder_test)

  function new(string name = "xif_slave_responder_test", uvm_component parent = null);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    cfg.active_passive = UVM_ACTIVE;
    cfg.role = XIF_ROLE_SLAVE_RESPONDER;
    cfg.flow_ctrl = XIF_FLOW_CTRL_BP;
    cfg.responder_mode = XIF_RESP_SHORT;
    cfg.short_min_cycles = 2;
    cfg.short_max_cycles = 2;
    cfg.timeout_cycles = 12;
    cfg.idle_pd_policy = XIF_IDLE_STABLE;
  endfunction

  task run_phase(uvm_phase phase);
    phase.raise_objection(this);

    fork
      drive_slave_side_vld(18);
      begin
        wait_reset_release();
        wait_cycles(6);
        vif.set_flow_force(XIF_FORCE_CLOSE);
        wait_cycles(3);
        vif.set_flow_force(XIF_FORCE_OPEN);
        wait_cycles(2);
        vif.set_flow_force(XIF_FORCE_RLS);
      end
    join

    wait_for_mon_items(18);
    expect_no_extra_mon_items();
    phase.drop_objection(this);
  endtask
endclass

`endif
