`ifndef XIF_MASTER_SLAVE_DUAL_TEST_SVH
`define XIF_MASTER_SLAVE_DUAL_TEST_SVH

class xif_master_slave_dual_test extends uvm_test;
  `uvm_component_utils(xif_master_slave_dual_test)

  xif_cfg                    master_agent_cfg;
  xif_cfg                    slave_agent_cfg;
  xif_dual_env #(xif_pd_t)   env;
  virtual xif_if #(xif_pd_t) master_vif;
  virtual xif_if #(xif_pd_t) slave_vif;

  function new(string name = "xif_master_slave_dual_test", uvm_component parent = null);
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

    env = xif_dual_env #(xif_pd_t)::type_id::create("env", this);

    if (!uvm_config_db#(virtual xif_if #(xif_pd_t))::get(this, "", "master_vif", master_vif)) begin
      `uvm_fatal("NOMASTERIF", "dual test requires master_vif")
    end
    if (!uvm_config_db#(virtual xif_if #(xif_pd_t))::get(this, "", "slave_vif", slave_vif)) begin
      `uvm_fatal("NOSLAVEIF", "dual test requires slave_vif")
    end

    uvm_config_db#(virtual xif_if #(xif_pd_t))::set(this, "env.master_agent", "vif", master_vif);
    uvm_config_db#(virtual xif_if #(xif_pd_t))::set(this, "env.slave_agent", "vif", slave_vif);
    uvm_config_db#(xif_cfg)::set(this, "env.master_agent", "cfg", master_agent_cfg);
    uvm_config_db#(xif_cfg)::set(this, "env.slave_agent", "cfg", slave_agent_cfg);
  endfunction

  task run_phase(uvm_phase phase);
    xif_multi_channel_outstanding_seq seq;
    xif_item #(xif_pd_t) item;
    int unsigned idx;

    phase.raise_objection(this);
    wait (master_vif.rst_n === 1'b1);
    @(posedge master_vif.clk);

    seq = xif_multi_channel_outstanding_seq::type_id::create("seq");
    seq.channels = 4;
    seq.ids_per_channel = 2;
    seq.max_outstanding = 4;
    seq.start(env.master_agent.sequencer);

    for (idx = 0; idx < 8; idx++) begin
      env.master_mon_fifo.get(item);
      `uvm_info("DUAL_MON", item.convert2string(), UVM_MEDIUM)
    end

    repeat (4) @(posedge master_vif.clk);
    phase.drop_objection(this);
  endtask
endclass

`endif
