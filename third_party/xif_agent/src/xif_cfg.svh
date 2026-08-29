`ifndef XIF_CFG_SVH
`define XIF_CFG_SVH

class xif_cfg extends uvm_object;
  rand uvm_active_passive_enum active_passive;
  rand xif_role_e              role;
  rand xif_flow_ctrl_e         flow_ctrl;
  rand xif_resp_mode_e         responder_mode;
  rand xif_idle_pd_policy_e    idle_pd_policy;

  rand int unsigned timeout_cycles;
  rand int unsigned short_min_cycles;
  rand int unsigned short_max_cycles;
  rand int unsigned long_min_cycles;
  rand int unsigned long_max_cycles;
  rand int unsigned pulse_period_cycles;
  rand int unsigned pulse_width_cycles;
  rand int unsigned random_probability_pct;
  rand int unsigned normal_switch_period;

  `uvm_object_utils_begin(xif_cfg)
    `uvm_field_enum(uvm_active_passive_enum, active_passive, UVM_DEFAULT)
    `uvm_field_enum(xif_role_e, role, UVM_DEFAULT)
    `uvm_field_enum(xif_flow_ctrl_e, flow_ctrl, UVM_DEFAULT)
    `uvm_field_enum(xif_resp_mode_e, responder_mode, UVM_DEFAULT)
    `uvm_field_enum(xif_idle_pd_policy_e, idle_pd_policy, UVM_DEFAULT)
    `uvm_field_int(timeout_cycles, UVM_DEFAULT)
    `uvm_field_int(short_min_cycles, UVM_DEFAULT)
    `uvm_field_int(short_max_cycles, UVM_DEFAULT)
    `uvm_field_int(long_min_cycles, UVM_DEFAULT)
    `uvm_field_int(long_max_cycles, UVM_DEFAULT)
    `uvm_field_int(pulse_period_cycles, UVM_DEFAULT)
    `uvm_field_int(pulse_width_cycles, UVM_DEFAULT)
    `uvm_field_int(random_probability_pct, UVM_DEFAULT)
    `uvm_field_int(normal_switch_period, UVM_DEFAULT)
  `uvm_object_utils_end

  constraint c_default {
    soft timeout_cycles == 5000;
    soft short_min_cycles dist { 1 :/ 1, [2:7] :/ 1, 4 :/ 1 };
    soft short_max_cycles dist { 1 :/ 1, [2:15] :/ 1, 8 :/ 1 };
    soft long_min_cycles dist { 100 :/ 1, [100:199] :/ 1, 200 :/ 1 };
    soft long_max_cycles dist { 100 :/ 1, [100:199] :/ 1, 200 :/ 1 };
    soft pulse_period_cycles dist { 20 :/ 1, [20:49] :/ 1, 50 :/ 1 };
    soft pulse_width_cycles dist { 1 :/ 1, [2:3] :/ 1, 4 :/ 1 };
    soft random_probability_pct dist { 0 :/ 1, [1:99] :/ 1, 25 :/ 1 };
    soft normal_switch_period dist { 1000 :/ 1, [1000:1999] :/ 1, 2000 :/ 1 };
  }

  function new(string name = "xif_cfg");
    super.new(name);
    active_passive         = UVM_ACTIVE;
    role                   = XIF_ROLE_MASTER;
    flow_ctrl              = XIF_FLOW_CTRL_NONE;
    responder_mode         = XIF_RESP_RLS;
    idle_pd_policy         = XIF_IDLE_STABLE;
    timeout_cycles         = 16;
    short_min_cycles       = 1;
    short_max_cycles       = 4;
    long_min_cycles        = 8;
    long_max_cycles        = 16;
    pulse_period_cycles    = 4;
    pulse_width_cycles     = 1;
    random_probability_pct = 25;
    normal_switch_period   = 8;
  endfunction

  function void sanitize();
    if (timeout_cycles == 0) begin
      timeout_cycles = 1;
    end

    if (short_min_cycles == 0) begin
      short_min_cycles = 1;
    end
    if (short_max_cycles < short_min_cycles) begin
      short_max_cycles = short_min_cycles;
    end

    if (long_min_cycles == 0) begin
      long_min_cycles = 1;
    end
    if (long_max_cycles < long_min_cycles) begin
      long_max_cycles = long_min_cycles;
    end

    if (pulse_period_cycles == 0) begin
      pulse_period_cycles = 1;
    end
    if (pulse_width_cycles == 0) begin
      pulse_width_cycles = 1;
    end
    if (pulse_width_cycles > pulse_period_cycles) begin
      pulse_width_cycles = pulse_period_cycles;
    end

    if (random_probability_pct > 100) begin
      random_probability_pct = 100;
    end

    if (normal_switch_period == 0) begin
      normal_switch_period = 1;
    end
  endfunction

  function string convert2string();
    return $sformatf(
      "active=%s role=%s flow=%s resp=%s idle=%0d timeout=%0d short=[%0d:%0d] long=[%0d:%0d] pulse=%0d/%0d rand=%0d normal=%0d",
      (active_passive == UVM_ACTIVE) ? "ACTIVE" : "PASSIVE",
      (role == XIF_ROLE_MASTER) ? "MASTER" : "SLAVE_RESPONDER",
      xif_flow_ctrl_name(flow_ctrl),
      xif_resp_mode_name(responder_mode),
      idle_pd_policy,
      timeout_cycles,
      short_min_cycles,
      short_max_cycles,
      long_min_cycles,
      long_max_cycles,
      pulse_period_cycles,
      pulse_width_cycles,
      random_probability_pct,
      normal_switch_period
    );
  endfunction
endclass

`endif
