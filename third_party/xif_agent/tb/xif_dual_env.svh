`ifndef XIF_DUAL_ENV_SVH
`define XIF_DUAL_ENV_SVH

class xif_dual_env #(type PD_T = logic [31:0]) extends uvm_env;
  `uvm_component_param_utils(xif_dual_env #(PD_T))

  xif_agent #(PD_T)                         master_agent;
  xif_agent #(PD_T)                         slave_agent;
  uvm_tlm_analysis_fifo #(xif_item #(PD_T)) master_mon_fifo;
  uvm_tlm_analysis_fifo #(xif_item #(PD_T)) slave_mon_fifo;

  function new(string name = "xif_dual_env", uvm_component parent = null);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    master_agent = xif_agent #(PD_T)::type_id::create("master_agent", this);
    slave_agent = xif_agent #(PD_T)::type_id::create("slave_agent", this);
    master_mon_fifo = new("master_mon_fifo", this);
    slave_mon_fifo = new("slave_mon_fifo", this);
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    master_agent.ap.connect(master_mon_fifo.analysis_export);
    slave_agent.ap.connect(slave_mon_fifo.analysis_export);
  endfunction
endclass

`endif
