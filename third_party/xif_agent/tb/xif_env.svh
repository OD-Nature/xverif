`ifndef XIF_ENV_SVH
`define XIF_ENV_SVH

class xif_env #(type PD_T = logic [31:0]) extends uvm_env;
  `uvm_component_param_utils(xif_env #(PD_T))

  xif_agent #(PD_T)                     agent;
  uvm_tlm_analysis_fifo #(xif_item #(PD_T)) mon_fifo;

  function new(string name = "xif_env", uvm_component parent = null);
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

`endif
