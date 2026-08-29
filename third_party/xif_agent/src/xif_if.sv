`ifndef XIF_IF_SV
`define XIF_IF_SV

interface xif_if #(
  type PD_T = logic [31:0],
  parameter real setup_time = 0.01, // ns
  parameter real hold_time  = 0.01  // ns
) (
  input logic clk,
  input logic rst_n
);
  import uvm_pkg::*;
  import xif_pkg::*;

  logic vld;
  logic rdy;
  logic bp;
  PD_T  pd;

  xif_cfg         cfg;
  xif_force_cmd_e forced_state;

  logic                 dbg_handshake;
  int unsigned          dbg_handshake_count;
  int unsigned          dbg_wait_count;
  int unsigned          dbg_success_streak;
  int unsigned          dbg_last_burst_len;
  xif_force_cmd_e       dbg_force_state;
  xif_resp_mode_e       dbg_effective_mode;

  int unsigned timeout_counter;
  int unsigned success_streak;

  bit          burst_phase_blocked;
  int unsigned phase_remaining;
  int unsigned pulse_counter;
  int unsigned pulse_width_remaining;
  xif_resp_mode_e normal_mode;
  bit             normal_mode_valid;
  int unsigned    normal_countdown;
  xif_resp_mode_e effective_mode_q;

`ifdef FCOV_ON
  int unsigned cg_wait_cycles;
  int unsigned cg_success_cycles;

  covergroup xif_hs_cg with function sample(int unsigned wait_cycles, int unsigned success_cycles);
    option.per_instance = 1;

    cp_wait: coverpoint wait_cycles {
      bins zero = {0};
      bins short = {[1:3]};
      bins medium = {[4:8]};
      bins long = {[9:32]};
      bins very_long = {[33:$]};
    }

    cp_success: coverpoint success_cycles {
      bins one = {1};
      bins few = {[2:4]};
      bins many = {[5:16]};
      bins burst = {[17:$]};
    }
  endgroup

  xif_hs_cg hs_cg = new();
`endif

  clocking drv_cb @(posedge clk);
    default input #setup_time output #hold_time;
    output vld;
    output pd;
    input  rdy;
    input  bp;
    input  rst_n;
  endclocking

  clocking mon_cb @(posedge clk);
    default input #setup_time output #hold_time;
    input vld;
    input rdy;
    input bp;
    input pd;
    input rst_n;
  endclocking

  function void set_cfg(xif_cfg cfg_h);
    cfg = cfg_h;
    if (cfg != null) begin
      cfg.sanitize();
    end
  endfunction

  function automatic xif_flow_ctrl_e flow_ctrl_mode();
    if (cfg == null) begin
      return XIF_FLOW_CTRL_NONE;
    end
    return cfg.flow_ctrl;
  endfunction

  function automatic bit responder_enabled();
    if (cfg == null) begin
      return 1'b0;
    end
    return (cfg.active_passive == UVM_ACTIVE) &&
           (cfg.role == XIF_ROLE_SLAVE_RESPONDER) &&
           (cfg.flow_ctrl != XIF_FLOW_CTRL_NONE);
  endfunction

  function automatic bit handshake_raw();
    return xif_handshake(vld, rdy, bp, flow_ctrl_mode());
  endfunction

  function automatic bit handshake_sampled();
    return xif_handshake(mon_cb.vld, mon_cb.rdy, mon_cb.bp, flow_ctrl_mode());
  endfunction

  function automatic int unsigned sample_burst_length(xif_resp_mode_e mode);
    int unsigned min_cycles;
    int unsigned max_cycles;

    if (cfg == null) begin
      return 1;
    end

    case (mode)
      XIF_RESP_SHORT: begin
        min_cycles = cfg.short_min_cycles;
        max_cycles = cfg.short_max_cycles;
      end
      default: begin
        min_cycles = cfg.long_min_cycles;
        max_cycles = cfg.long_max_cycles;
      end
    endcase

    if (max_cycles < min_cycles) begin
      max_cycles = min_cycles;
    end

    return $urandom_range(max_cycles, min_cycles);
  endfunction

  task automatic reset_responder_state();
    burst_phase_blocked  = 1'b1;
    phase_remaining      = 0;
    pulse_counter        = 0;
    pulse_width_remaining = 0;
    normal_mode_valid    = 1'b0;
    normal_countdown     = 0;
    effective_mode_q     = XIF_RESP_RLS;
    dbg_last_burst_len   = 0;
    dbg_effective_mode   = XIF_RESP_RLS;
  endtask

  task automatic drive_flow(bit allow_transfer);
    case (flow_ctrl_mode())
      XIF_FLOW_CTRL_RDY: begin
        rdy <= allow_transfer;
        bp  <= 1'b0;
      end
      XIF_FLOW_CTRL_BP: begin
        bp  <= !allow_transfer;
        rdy <= 1'b0;
      end
      default: begin
        rdy <= 1'b0;
        bp  <= 1'b0;
      end
    endcase
  endtask

  task automatic drive_blocking_flow();
    case (flow_ctrl_mode())
      XIF_FLOW_CTRL_RDY: begin
        rdy <= 1'b0;
        bp  <= 1'b0;
      end
      XIF_FLOW_CTRL_BP: begin
        bp  <= 1'b1;
        rdy <= 1'b0;
      end
      default: begin
        rdy <= 1'b0;
        bp  <= 1'b0;
      end
    endcase
  endtask

  task automatic select_effective_mode(output xif_resp_mode_e mode);
    if (cfg == null) begin
      mode = XIF_RESP_RLS;
      dbg_effective_mode = mode;
      return;
    end

    mode = cfg.responder_mode;
    if (mode == XIF_RESP_NORMAL) begin
      if ((!normal_mode_valid) || (normal_countdown == 0)) begin
        normal_mode = xif_pick_normal_mode();
        normal_mode_valid = 1'b1;
        normal_countdown = cfg.normal_switch_period;
      end
      mode = normal_mode;
      if (normal_countdown > 0) begin
        normal_countdown--;
      end
    end else begin
      normal_mode_valid = 1'b0;
      normal_countdown = 0;
    end

    if (mode != effective_mode_q) begin
      burst_phase_blocked = 1'b1;
      phase_remaining = 0;
      pulse_counter = 0;
      pulse_width_remaining = 0;
      dbg_last_burst_len = 0;
      effective_mode_q = mode;
    end

    dbg_effective_mode = mode;
  endtask

  task automatic drive_burst_mode(xif_resp_mode_e mode);
    if (phase_remaining == 0) begin
      burst_phase_blocked = !burst_phase_blocked;
      if (burst_phase_blocked) begin
        phase_remaining = sample_burst_length(mode);
        dbg_last_burst_len = phase_remaining;
      end else begin
        phase_remaining = 1;
      end
    end

    drive_flow(!burst_phase_blocked);

    if (phase_remaining > 0) begin
      phase_remaining--;
    end
  endtask

  task automatic drive_pulse_mode();
    if (cfg == null) begin
      drive_flow(1'b1);
      return;
    end

    if (pulse_width_remaining != 0) begin
      drive_flow(1'b0);
      pulse_width_remaining--;
      return;
    end

    if ((pulse_counter + 1) >= cfg.pulse_period_cycles) begin
      drive_flow(1'b0);
      pulse_counter = 0;
      if (cfg.pulse_width_cycles > 1) begin
        pulse_width_remaining = cfg.pulse_width_cycles - 1;
      end
    end else begin
      drive_flow(1'b1);
      pulse_counter++;
    end
  endtask

  task automatic set_flow_force(xif_force_cmd_e cmd);
    forced_state = cmd;
    dbg_force_state = cmd;

    case (flow_ctrl_mode())
      XIF_FLOW_CTRL_RDY: begin
        case (cmd)
          XIF_FORCE_OPEN:  force rdy = 1'b1;
          XIF_FORCE_CLOSE: force rdy = 1'b0;
          default:         release rdy;
        endcase
      end
      XIF_FLOW_CTRL_BP: begin
        case (cmd)
          XIF_FORCE_OPEN:  force bp = 1'b0;
          XIF_FORCE_CLOSE: force bp = 1'b1;
          default:         release bp;
        endcase
      end
      default: begin
      end
    endcase
  endtask

  initial begin
    vld = 1'b0;
    rdy = 1'b0;
    bp  = 1'b0;
    pd  = '0;
    forced_state = XIF_FORCE_RLS;
    dbg_force_state = XIF_FORCE_RLS;
    dbg_handshake = 1'b0;
    dbg_handshake_count = 0;
    dbg_wait_count = 0;
    dbg_success_streak = 0;
    timeout_counter = 0;
    success_streak = 0;
    reset_responder_state();
  end

  always @(posedge clk) begin
    xif_resp_mode_e mode;

    if (!responder_enabled()) begin
      reset_responder_state();
    end else if (!rst_n) begin
      drive_blocking_flow();
      reset_responder_state();
    end else if (forced_state != XIF_FORCE_RLS) begin
      reset_responder_state();
    end else begin
      select_effective_mode(mode);
      case (mode)
        XIF_RESP_SHORT,
        XIF_RESP_LONG:   drive_burst_mode(mode);
        XIF_RESP_PULSE:  drive_pulse_mode();
        XIF_RESP_RANDOM: begin
          if ($urandom_range(0, 99) < cfg.random_probability_pct) begin
            drive_flow(1'b0);
          end else begin
            drive_flow(1'b1);
          end
        end
        default:         drive_flow(1'b1);
      endcase
    end
  end

  property p_no_handshake_during_reset;
    @(posedge clk) !rst_n |-> !handshake_raw();
  endproperty

  property p_vld_held_while_blocked;
    @(posedge clk) disable iff (!rst_n)
      xif_blocked(vld, rdy, bp, flow_ctrl_mode()) |=> (vld === 1'b1);
  endproperty

  property p_pd_stable_while_blocked;
    @(posedge clk) disable iff (!rst_n)
      xif_blocked(vld, rdy, bp, flow_ctrl_mode()) |=> $stable(pd);
  endproperty

  a_no_handshake_during_reset: assert property (p_no_handshake_during_reset)
    else uvm_report_error("XIF_RESET_HS", $sformatf("handshake observed during reset at %0t", $time), UVM_NONE);

  a_vld_held_while_blocked: assert property (p_vld_held_while_blocked)
    else uvm_report_error("XIF_VLD_DROP", $sformatf("vld dropped while blocked at %0t", $time), UVM_NONE);

  a_pd_stable_while_blocked: assert property (p_pd_stable_while_blocked)
    else uvm_report_error("XIF_PD_UNSTABLE", $sformatf("pd changed while blocked at %0t", $time), UVM_NONE);

  always @(posedge clk) begin
    bit handshake;
    logic [$bits(PD_T)-1:0] pd_bits;

    handshake = handshake_sampled();
    dbg_handshake = handshake;

    if (!rst_n) begin
      timeout_counter = 0;
      success_streak = 0;
      dbg_wait_count = 0;
      dbg_success_streak = 0;
    end else begin
      if (mon_cb.vld === 1'b1) begin
        pd_bits = mon_cb.pd;
        if ($isunknown(pd_bits)) begin
          uvm_report_error("XIF_PD_X", $sformatf("pd contains X/Z while vld is asserted at %0t", $time), UVM_NONE);
        end

        case (flow_ctrl_mode())
          XIF_FLOW_CTRL_RDY: begin
            if ($isunknown(mon_cb.rdy)) begin
              uvm_report_error("XIF_RDY_X", $sformatf("rdy contains X/Z while vld is asserted at %0t", $time), UVM_NONE);
            end
          end
          XIF_FLOW_CTRL_BP: begin
            if ($isunknown(mon_cb.bp)) begin
              uvm_report_error("XIF_BP_X", $sformatf("bp contains X/Z while vld is asserted at %0t", $time), UVM_NONE);
            end
          end
          default: begin
          end
        endcase
      end

      if ((flow_ctrl_mode() != XIF_FLOW_CTRL_NONE) && (mon_cb.vld === 1'b1) && !handshake) begin
        timeout_counter++;
        dbg_wait_count = timeout_counter;
        if ((cfg != null) && (timeout_counter == cfg.timeout_cycles)) begin
          uvm_report_error(
            "XIF_TIMEOUT",
            $sformatf(
              "flow control timeout after %0d cycles (mode=%s) at %0t",
              timeout_counter,
              xif_flow_ctrl_name(flow_ctrl_mode()),
              $time
            ),
            UVM_NONE
          );
        end
      end else begin
        timeout_counter = 0;
        dbg_wait_count = 0;
      end

      if (handshake) begin
        success_streak++;
        dbg_handshake_count++;
        dbg_success_streak = success_streak;
`ifdef FCOV_ON
        cg_wait_cycles = timeout_counter;
        cg_success_cycles = success_streak;
        hs_cg.sample(cg_wait_cycles, cg_success_cycles);
`endif
      end else begin
        success_streak = 0;
        dbg_success_streak = 0;
      end
    end
  end
endinterface

`endif
