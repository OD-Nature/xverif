`ifndef MODE02_SLAVE_RESPONDER_CONTROL_PKG_SV
`define MODE02_SLAVE_RESPONDER_CONTROL_PKG_SV

package mode02_slave_responder_control_pkg;
  import uvm_pkg::*;
  import xif_pkg::*;
  import xif_agent_pkg::*;
  `include "uvm_macros.svh"

  // ============================
  // PD_T definition
  // ============================
  typedef struct packed {
    logic [7:0]  opcode;
    logic [15:0] data;
  } mode02_pd_t;

  // ============================
  // Environment
  // ============================
  class mode02_env #(type PD_T = mode02_pd_t) extends uvm_env;
    `uvm_component_param_utils(mode02_env #(PD_T))

    xif_agent #(PD_T)                         agent;
    uvm_tlm_analysis_fifo #(xif_item #(PD_T)) mon_fifo;

    function new(string name = "mode02_env", uvm_component parent = null);
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

  // ============================
  // Base test with helpers
  // ============================
  class mode02_base_test extends uvm_test;
    `uvm_component_utils(mode02_base_test)

    xif_cfg                           cfg;
    mode02_env #(mode02_pd_t)         env;
    virtual xif_if #(mode02_pd_t)     vif;

    function new(string name = "mode02_base_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      cfg = xif_cfg::type_id::create("cfg");
      env = mode02_env #(mode02_pd_t)::type_id::create("env", this);
      if (!uvm_config_db#(virtual xif_if #(mode02_pd_t))::get(this, "", "vif", vif)) begin
        `uvm_fatal("NOVIF", "test requires virtual interface")
      end
      uvm_config_db#(xif_cfg)::set(this, "env*", "cfg", cfg);
      uvm_config_db#(virtual xif_if #(mode02_pd_t))::set(this, "env*", "vif", vif);
      vif.set_cfg(cfg);
    endfunction

    task automatic wait_reset_release();
      wait (vif.rst_n === 1'b1);
      @(posedge vif.clk);
    endtask

    task automatic wait_cycles(int unsigned cycles);
      repeat (cycles) @(posedge vif.clk);
    endtask

    task automatic wait_sampled_handshake();
      do begin
        @(posedge vif.clk);
        #1ns;
      end while (vif.dbg_handshake !== 1'b1);
    endtask

    task automatic wait_for_mon_items(int unsigned count, time timeout = 5000ns);
      int unsigned seen;
      bit timeout_hit;
      fork : wait_mon_fork
        begin
          xif_item #(mode02_pd_t) item;
          for (seen = 0; seen < count; seen++) begin
            env.mon_fifo.get(item);
            `uvm_info("MONITEM", item.convert2string(), UVM_MEDIUM)
          end
        end
        begin
          #(timeout);
          timeout_hit = 1'b1;
        end
      join_any
      disable wait_mon_fork;
      if (timeout_hit) begin
        `uvm_fatal("TIMEOUT", $sformatf("Timed out waiting for %0d monitor items", count))
      end
    endtask

    task automatic expect_no_extra_mon_items(int unsigned settle_cycles = 2);
      xif_item #(mode02_pd_t) item;
      wait_cycles(settle_cycles);
      if (env.mon_fifo.try_get(item)) begin
        `uvm_fatal("EXTRA_MONITEM", $sformatf("Unexpected extra monitor item: %s", item.convert2string()))
      end
    endtask

    task automatic drive_slave_side_vld(int unsigned cycles);
      mode02_pd_t payload;
      int unsigned idx;

      wait_reset_release();
      vif.vld = 1'b0;
      vif.pd = '0;
      wait_cycles(2);

      for (idx = 0; idx < cycles; idx++) begin
        payload.opcode = 8'h80 + idx[7:0];
        payload.data   = 16'h2000 + idx[15:0];
        @(negedge vif.clk);
        vif.vld = 1'b1;
        vif.pd = payload;
        wait_sampled_handshake();
        vif.vld = 1'b0;
      end

      @(negedge vif.clk);
      vif.vld = 1'b0;
    endtask
  endclass

  // ============================
  // Concrete test
  // ============================
  class mode02_slave_responder_control_test extends mode02_base_test;
    `uvm_component_utils(mode02_slave_responder_control_test)

    function new(string name = "mode02_slave_responder_control_test", uvm_component parent = null);
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

endpackage

`endif
