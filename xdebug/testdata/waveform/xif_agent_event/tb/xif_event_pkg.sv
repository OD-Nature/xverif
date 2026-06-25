`ifndef XIF_EVENT_PKG_SV
`define XIF_EVENT_PKG_SV

package xif_event_pkg;
  import uvm_pkg::*;
  import xif_pkg::*;
  import xif_agent_pkg::*;
  `include "uvm_macros.svh"

  typedef struct packed {
    logic [7:0]  opcode;
    logic [3:0]  channel;
    logic [3:0]  id;
    logic [15:0] data;
  } xif_event_pd_t;

  typedef xif_item #(xif_event_pd_t) xif_event_item_t;
  typedef xif_agent #(xif_event_pd_t) xif_event_agent_t;

  class xif_event_env extends uvm_env;
    `uvm_component_utils(xif_event_env)

    xif_event_agent_t rdy_agent;
    xif_event_agent_t bp_agent;
    xif_event_agent_t none_agent;
    xif_event_agent_t pair_master_agent;
    xif_event_agent_t pair_slave_agent;

    uvm_tlm_analysis_fifo #(xif_event_item_t) rdy_fifo;
    uvm_tlm_analysis_fifo #(xif_event_item_t) bp_fifo;
    uvm_tlm_analysis_fifo #(xif_event_item_t) none_fifo;
    uvm_tlm_analysis_fifo #(xif_event_item_t) pair_master_fifo;
    uvm_tlm_analysis_fifo #(xif_event_item_t) pair_slave_fifo;

    function new(string name = "xif_event_env", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      rdy_agent = xif_event_agent_t::type_id::create("rdy_agent", this);
      bp_agent = xif_event_agent_t::type_id::create("bp_agent", this);
      none_agent = xif_event_agent_t::type_id::create("none_agent", this);
      pair_master_agent = xif_event_agent_t::type_id::create("pair_master_agent", this);
      pair_slave_agent = xif_event_agent_t::type_id::create("pair_slave_agent", this);
      rdy_fifo = new("rdy_fifo", this);
      bp_fifo = new("bp_fifo", this);
      none_fifo = new("none_fifo", this);
      pair_master_fifo = new("pair_master_fifo", this);
      pair_slave_fifo = new("pair_slave_fifo", this);
    endfunction

    function void connect_phase(uvm_phase phase);
      super.connect_phase(phase);
      rdy_agent.ap.connect(rdy_fifo.analysis_export);
      bp_agent.ap.connect(bp_fifo.analysis_export);
      none_agent.ap.connect(none_fifo.analysis_export);
      pair_master_agent.ap.connect(pair_master_fifo.analysis_export);
      pair_slave_agent.ap.connect(pair_slave_fifo.analysis_export);
    endfunction
  endclass

  class xif_event_base_seq extends uvm_sequence #(xif_event_item_t);
    `uvm_object_utils(xif_event_base_seq)

    function new(string name = "xif_event_base_seq");
      super.new(name);
    endfunction

    task automatic send_item(logic [7:0] opcode,
                             logic [3:0] channel,
                             logic [3:0] id,
                             logic [15:0] data,
                             int unsigned leading = 0,
                             int unsigned post = 0);
      xif_event_item_t req;
      req = xif_event_item_t::type_id::create($sformatf("req_%02x_%0d_%0d_%04x", opcode, channel, id, data));
      req.pd.opcode = opcode;
      req.pd.channel = channel;
      req.pd.id = id;
      req.pd.data = data;
      req.leading_cycles = leading;
      req.post_cycles = post;
      start_item(req);
      finish_item(req);
    endtask
  endclass

  class xif_event_rdy_seq extends xif_event_base_seq;
    `uvm_object_utils(xif_event_rdy_seq)

    function new(string name = "xif_event_rdy_seq");
      super.new(name);
    endfunction

    task body();
      send_item(8'h5a, 4'h3, 4'h2, 16'ha55a, 0, 0);
      send_item(8'h5a, 4'h3, 4'h2, 16'ha55a, 0, 0);
      send_item(8'h10, 4'h1, 4'h1, 16'h1000, 0, 0);
      send_item(8'h11, 4'h2, 4'h0, 16'h1001, 1, 0);
      send_item(8'h12, 4'h3, 4'h2, 16'h1002, 0, 0);
    endtask
  endclass

  class xif_event_bp_seq extends xif_event_base_seq;
    `uvm_object_utils(xif_event_bp_seq)

    function new(string name = "xif_event_bp_seq");
      super.new(name);
    endfunction

    task body();
      send_item(8'hb0, 4'h0, 4'h0, 16'h2000, 0, 0);
      send_item(8'hb1, 4'h1, 4'h1, 16'h2001, 0, 0);
      send_item(8'hb2, 4'h2, 4'h2, 16'h2002, 1, 0);
      send_item(8'hb3, 4'h3, 4'h3, 16'h2003, 0, 0);
    endtask
  endclass

  class xif_event_none_seq extends xif_event_base_seq;
    `uvm_object_utils(xif_event_none_seq)

    function new(string name = "xif_event_none_seq");
      super.new(name);
    endfunction

    task body();
      send_item(8'hc0, 4'h0, 4'h1, 16'h3000, 0, 1);
      send_item(8'hc1, 4'h1, 4'h2, 16'h3001, 2, 0);
      send_item(8'hc2, 4'h2, 4'h3, 16'h3002, 0, 0);
    endtask
  endclass

  class xif_event_pair_seq extends xif_event_base_seq;
    `uvm_object_utils(xif_event_pair_seq)

    function new(string name = "xif_event_pair_seq");
      super.new(name);
    endfunction

    task body();
      send_item(8'hd0, 4'h0, 4'h0, 16'h4000, 0, 0);
      send_item(8'hd1, 4'h1, 4'h1, 16'h4001, 0, 0);
      send_item(8'hd2, 4'h2, 4'h2, 16'h4002, 0, 0);
      send_item(8'hd3, 4'h3, 4'h3, 16'h4003, 0, 0);
    endtask
  endclass

  class xif_event_multi_if_test extends uvm_test;
    `uvm_component_utils(xif_event_multi_if_test)

    xif_event_env env;
    xif_cfg rdy_cfg;
    xif_cfg bp_cfg;
    xif_cfg none_cfg;
    xif_cfg pair_master_cfg;
    xif_cfg pair_slave_cfg;

    virtual xif_if #(xif_event_pd_t) if_rdy;
    virtual xif_if #(xif_event_pd_t) if_bp;
    virtual xif_if #(xif_event_pd_t) if_none;
    virtual xif_if #(xif_event_pd_t) if_pair_master;
    virtual xif_if #(xif_event_pd_t) if_pair_slave;

    function new(string name = "xif_event_multi_if_test", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);

      env = xif_event_env::type_id::create("env", this);

      if (!uvm_config_db#(virtual xif_if #(xif_event_pd_t))::get(this, "", "if_rdy", if_rdy)) begin
        `uvm_fatal("NO_IF_RDY", "missing if_rdy")
      end
      if (!uvm_config_db#(virtual xif_if #(xif_event_pd_t))::get(this, "", "if_bp", if_bp)) begin
        `uvm_fatal("NO_IF_BP", "missing if_bp")
      end
      if (!uvm_config_db#(virtual xif_if #(xif_event_pd_t))::get(this, "", "if_none", if_none)) begin
        `uvm_fatal("NO_IF_NONE", "missing if_none")
      end
      if (!uvm_config_db#(virtual xif_if #(xif_event_pd_t))::get(this, "", "if_pair_master", if_pair_master)) begin
        `uvm_fatal("NO_IF_PAIR_M", "missing if_pair_master")
      end
      if (!uvm_config_db#(virtual xif_if #(xif_event_pd_t))::get(this, "", "if_pair_slave", if_pair_slave)) begin
        `uvm_fatal("NO_IF_PAIR_S", "missing if_pair_slave")
      end

      rdy_cfg = xif_cfg::type_id::create("rdy_cfg");
      rdy_cfg.active_passive = UVM_ACTIVE;
      rdy_cfg.role = XIF_ROLE_MASTER;
      rdy_cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
      rdy_cfg.timeout_cycles = 32;

      bp_cfg = xif_cfg::type_id::create("bp_cfg");
      bp_cfg.active_passive = UVM_ACTIVE;
      bp_cfg.role = XIF_ROLE_MASTER;
      bp_cfg.flow_ctrl = XIF_FLOW_CTRL_BP;
      bp_cfg.timeout_cycles = 32;

      none_cfg = xif_cfg::type_id::create("none_cfg");
      none_cfg.active_passive = UVM_ACTIVE;
      none_cfg.role = XIF_ROLE_MASTER;
      none_cfg.flow_ctrl = XIF_FLOW_CTRL_NONE;
      none_cfg.timeout_cycles = 32;

      pair_master_cfg = xif_cfg::type_id::create("pair_master_cfg");
      pair_master_cfg.active_passive = UVM_ACTIVE;
      pair_master_cfg.role = XIF_ROLE_MASTER;
      pair_master_cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
      pair_master_cfg.timeout_cycles = 32;

      pair_slave_cfg = xif_cfg::type_id::create("pair_slave_cfg");
      pair_slave_cfg.active_passive = UVM_ACTIVE;
      pair_slave_cfg.role = XIF_ROLE_SLAVE_RESPONDER;
      pair_slave_cfg.flow_ctrl = XIF_FLOW_CTRL_RDY;
      pair_slave_cfg.responder_mode = XIF_RESP_PULSE;
      pair_slave_cfg.pulse_period_cycles = 3;
      pair_slave_cfg.pulse_width_cycles = 1;
      pair_slave_cfg.timeout_cycles = 32;

      uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(this, "env.rdy_agent", "vif", if_rdy);
      uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(this, "env.bp_agent", "vif", if_bp);
      uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(this, "env.none_agent", "vif", if_none);
      uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(this, "env.pair_master_agent", "vif", if_pair_master);
      uvm_config_db#(virtual xif_if #(xif_event_pd_t))::set(this, "env.pair_slave_agent", "vif", if_pair_slave);

      uvm_config_db#(xif_cfg)::set(this, "env.rdy_agent", "cfg", rdy_cfg);
      uvm_config_db#(xif_cfg)::set(this, "env.bp_agent", "cfg", bp_cfg);
      uvm_config_db#(xif_cfg)::set(this, "env.none_agent", "cfg", none_cfg);
      uvm_config_db#(xif_cfg)::set(this, "env.pair_master_agent", "cfg", pair_master_cfg);
      uvm_config_db#(xif_cfg)::set(this, "env.pair_slave_agent", "cfg", pair_slave_cfg);
    endfunction

    task automatic wait_reset_release();
      wait (if_rdy.rst_n === 1'b1);
      @(posedge if_rdy.clk);
    endtask

    task automatic drive_rdy_flow();
      wait_reset_release();
      if_rdy.bp <= 1'b0;
      if_rdy.rdy <= 1'b0;
      repeat (2) @(posedge if_rdy.clk);
      repeat (80) begin
        if_rdy.rdy <= 1'b1;
        @(posedge if_rdy.clk);
      end
    endtask

    task automatic drive_bp_flow();
      wait_reset_release();
      if_bp.rdy <= 1'b0;
      if_bp.bp <= 1'b1;
      repeat (3) @(posedge if_bp.clk);
      repeat (80) begin
        if_bp.bp <= 1'b0;
        @(posedge if_bp.clk);
      end
    endtask

    task automatic drive_none_defaults();
      wait_reset_release();
      repeat (80) begin
        if_none.rdy <= 1'b0;
        if_none.bp <= 1'b0;
        @(posedge if_none.clk);
      end
    endtask

    task automatic wait_fifo_items(uvm_tlm_analysis_fifo #(xif_event_item_t) fifo,
                                   int unsigned count,
                                   string label);
      xif_event_item_t item;
      int unsigned idx;
      bit timeout_hit;

      fork : wait_items
        begin
          for (idx = 0; idx < count; idx++) begin
            fifo.get(item);
            `uvm_info("XIF_EVENT_OBS", $sformatf("%s[%0d] %s", label, idx, item.convert2string()), UVM_MEDIUM)
          end
        end
        begin
          #5000ns;
          timeout_hit = 1'b1;
        end
      join_any
      disable wait_items;

      if (timeout_hit) begin
        `uvm_fatal("XIF_EVENT_TIMEOUT", $sformatf("timeout waiting for %0d %s items", count, label))
      end
    endtask

    task run_phase(uvm_phase phase);
      xif_event_rdy_seq rdy_seq;
      xif_event_bp_seq bp_seq;
      xif_event_none_seq none_seq;
      xif_event_pair_seq pair_seq;

      phase.raise_objection(this);

      fork
        drive_rdy_flow();
        drive_bp_flow();
        drive_none_defaults();
      join_none

      wait_reset_release();

      rdy_seq = xif_event_rdy_seq::type_id::create("rdy_seq");
      bp_seq = xif_event_bp_seq::type_id::create("bp_seq");
      none_seq = xif_event_none_seq::type_id::create("none_seq");
      pair_seq = xif_event_pair_seq::type_id::create("pair_seq");

      fork
        rdy_seq.start(env.rdy_agent.sequencer);
        bp_seq.start(env.bp_agent.sequencer);
        none_seq.start(env.none_agent.sequencer);
        pair_seq.start(env.pair_master_agent.sequencer);
      join

      wait_fifo_items(env.rdy_fifo, 5, "rdy");
      wait_fifo_items(env.bp_fifo, 4, "bp");
      wait_fifo_items(env.none_fifo, 3, "none");
      wait_fifo_items(env.pair_master_fifo, 4, "pair_master");
      wait_fifo_items(env.pair_slave_fifo, 4, "pair_slave");

      repeat (6) @(posedge if_rdy.clk);
      phase.drop_objection(this);
    endtask
  endclass
endpackage

`endif
