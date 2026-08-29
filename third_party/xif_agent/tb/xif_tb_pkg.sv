`ifndef XIF_TB_PKG_SV
`define XIF_TB_PKG_SV

package xif_tb_pkg;
  import uvm_pkg::*;
  import xif_pkg::*;
  import xif_agent_pkg::*;
  `include "uvm_macros.svh"

  typedef struct packed {
    logic [7:0]  opcode;
    logic [15:0] data;
  } xif_pd_t;

  typedef struct packed {
    logic [3:0]  tag;
    logic [31:0] payload;
  } xif_alt_pd_t;

  typedef xif_item #(xif_alt_pd_t)      xif_alt_item_t;
  typedef xif_sequencer #(xif_alt_pd_t) xif_alt_sequencer_t;
  typedef xif_driver #(xif_alt_pd_t)    xif_alt_driver_t;
  typedef xif_monitor #(xif_alt_pd_t)   xif_alt_monitor_t;
  typedef xif_agent #(xif_alt_pd_t)     xif_alt_agent_t;

  `include "xif_env.svh"
  typedef xif_env #(xif_alt_pd_t)       xif_alt_env_t;
  `include "xif_dual_env.svh"

  `include "xif_smoke_seq.svh"
  `include "xif_duplicate_pd_seq.svh"
  `include "xif_complex_seq.svh"
  `include "xif_base_test.svh"
  `include "xif_master_rdy_test.svh"
  `include "xif_master_bp_test.svh"
  `include "xif_master_none_test.svh"
  `include "xif_master_duplicate_pd_test.svh"
  `include "xif_slave_responder_test.svh"
  `include "xif_passive_monitor_test.svh"
  `include "xif_complex_sequence_test.svh"
  `include "xif_master_slave_dual_test.svh"
endpackage

`endif
