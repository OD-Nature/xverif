`ifndef XIF_MONITOR_SVH
`define XIF_MONITOR_SVH

class xif_monitor #(type PD_T = logic [31:0]) extends uvm_component;
  `uvm_component_param_utils(xif_monitor #(PD_T))

  virtual xif_if #(PD_T)                  vif;
  xif_cfg                                 cfg;
  uvm_analysis_port #(xif_item #(PD_T))   ap;

  function new(string name = "xif_monitor", uvm_component parent = null);
    super.new(name, parent);
    ap = new("ap", this);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);

    if (!uvm_config_db#(virtual xif_if #(PD_T))::get(this, "", "vif", vif)) begin
      `uvm_fatal("NOVIF", "xif_monitor requires a virtual interface")
    end

    if (!uvm_config_db#(xif_cfg)::get(this, "", "cfg", cfg)) begin
      `uvm_fatal("NOCFG", "xif_monitor requires xif_cfg")
    end

    cfg.sanitize();
  endfunction

  task run_phase(uvm_phase phase);
    xif_item #(PD_T) item;

    forever begin
      @vif.mon_cb;

      if (!vif.mon_cb.rst_n) begin
        continue;
      end

      if (xif_handshake(vif.mon_cb.vld, vif.mon_cb.rdy, vif.mon_cb.bp, cfg.flow_ctrl)) begin
        item = xif_item #(PD_T)::type_id::create("item", this);
        item.pd = vif.mon_cb.pd;
        item.leading_cycles = 0;
        item.post_cycles = 0;
        `uvm_info("XIF_MON_HS", $sformatf("monitor observed handshake item %s", item.convert2string()), UVM_MEDIUM)
        ap.write(item);
      end
    end
  endtask
endclass

`endif
