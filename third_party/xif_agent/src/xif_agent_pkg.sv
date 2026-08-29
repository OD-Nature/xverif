`ifndef XIF_AGENT_PKG_SV
`define XIF_AGENT_PKG_SV

package xif_agent_pkg;
  import uvm_pkg::*;
  import xif_pkg::*;
  `include "uvm_macros.svh"

  `include "xif_item.svh"
  `include "xif_sequencer.svh"
  `include "xif_driver.svh"
  `include "xif_monitor.svh"
  `include "xif_agent.svh"
endpackage

`endif
