`ifndef XIF_PKG_SV
`define XIF_PKG_SV

package xif_pkg;
  import uvm_pkg::*;
  `include "uvm_macros.svh"

  typedef enum bit [0:0] {
    XIF_ROLE_MASTER           = 1'b0,
    XIF_ROLE_SLAVE_RESPONDER  = 1'b1
  } xif_role_e;

  typedef enum bit [1:0] {
    XIF_FLOW_CTRL_NONE = 2'd0,
    XIF_FLOW_CTRL_RDY  = 2'd1,
    XIF_FLOW_CTRL_BP   = 2'd2
  } xif_flow_ctrl_e;

  typedef enum bit [2:0] {
    XIF_RESP_RLS    = 3'd0,
    XIF_RESP_SHORT  = 3'd1,
    XIF_RESP_LONG   = 3'd2,
    XIF_RESP_PULSE  = 3'd3,
    XIF_RESP_RANDOM = 3'd4,
    XIF_RESP_NORMAL = 3'd5
  } xif_resp_mode_e;

  typedef enum bit [1:0] {
    XIF_IDLE_STABLE      = 2'd0,
    XIF_IDLE_X_ONLY      = 2'd1,
    XIF_IDLE_FULL_RANDOM = 2'd2
  } xif_idle_pd_policy_e;

  typedef enum bit [1:0] {
    XIF_FORCE_OPEN  = 2'd0,
    XIF_FORCE_CLOSE = 2'd1,
    XIF_FORCE_RLS   = 2'd2
  } xif_force_cmd_e;

  function automatic bit xif_handshake(
    logic vld,
    logic rdy,
    logic bp,
    xif_flow_ctrl_e mode
  );
    case (mode)
      XIF_FLOW_CTRL_RDY:  return (vld === 1'b1) && (rdy === 1'b1);
      default:            return (vld === 1'b1);
    endcase
  endfunction

  function automatic bit xif_blocked(
    logic vld,
    logic rdy,
    logic bp,
    xif_flow_ctrl_e mode
  );
    if (vld !== 1'b1) begin
      return 1'b0;
    end

    case (mode)
      XIF_FLOW_CTRL_RDY:  return (rdy !== 1'b1);
      default:            return 1'b0;
    endcase
  endfunction

  function automatic string xif_flow_ctrl_name(xif_flow_ctrl_e mode);
    case (mode)
      XIF_FLOW_CTRL_RDY:  return "RDY";
      XIF_FLOW_CTRL_BP:   return "BP";
      default:            return "NONE";
    endcase
  endfunction

  function automatic string xif_resp_mode_name(xif_resp_mode_e mode);
    case (mode)
      XIF_RESP_SHORT:   return "SHORT";
      XIF_RESP_LONG:    return "LONG";
      XIF_RESP_PULSE:   return "PULSE";
      XIF_RESP_RANDOM:  return "RANDOM";
      XIF_RESP_NORMAL:  return "NORMAL";
      default:          return "RLS";
    endcase
  endfunction

  function automatic xif_resp_mode_e xif_pick_normal_mode();
    case ($urandom_range(0, 3))
      0:       return XIF_RESP_SHORT;
      1:       return XIF_RESP_LONG;
      2:       return XIF_RESP_PULSE;
      default: return XIF_RESP_RANDOM;
    endcase
  endfunction

  `include "xif_cfg.svh"
endpackage

`endif
