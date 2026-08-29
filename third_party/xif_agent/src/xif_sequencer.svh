`ifndef XIF_SEQUENCER_SVH
`define XIF_SEQUENCER_SVH

class xif_sequencer #(type PD_T = logic [31:0]) extends uvm_sequencer #(xif_item #(PD_T));
  `uvm_component_param_utils(xif_sequencer #(PD_T))

  function new(string name = "xif_sequencer", uvm_component parent = null);
    super.new(name, parent);
  endfunction
endclass

`endif
