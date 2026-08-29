`ifndef XIF_AGENT_SVH
`define XIF_AGENT_SVH

class xif_agent #(type PD_T = logic [31:0]) extends uvm_agent;
  `uvm_component_param_utils(xif_agent #(PD_T))

  xif_cfg                               cfg;
  virtual xif_if #(PD_T)                vif;

  xif_sequencer #(PD_T)                 sequencer;
  xif_driver #(PD_T)                    driver;
  xif_monitor #(PD_T)                   monitor;
  uvm_analysis_port #(xif_item #(PD_T)) ap;

  function new(string name = "xif_agent", uvm_component parent = null);
    super.new(name, parent);
    ap = new("ap", this);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);

    if (!uvm_config_db#(virtual xif_if #(PD_T))::get(this, "", "vif", vif)) begin
      `uvm_fatal("NOVIF", "xif_agent requires a virtual interface")
    end

    if (!uvm_config_db#(xif_cfg)::get(this, "", "cfg", cfg)) begin
      cfg = xif_cfg::type_id::create("cfg");
      `uvm_warning("CFGDEFAULT", "xif_agent did not receive cfg, using defaults")
    end

    cfg.sanitize();
    vif.set_cfg(cfg);

    uvm_config_db#(virtual xif_if #(PD_T))::set(this, "monitor", "vif", vif);
    uvm_config_db#(xif_cfg)::set(this, "monitor", "cfg", cfg);
    monitor = xif_monitor #(PD_T)::type_id::create("monitor", this);

    if ((cfg.active_passive == UVM_ACTIVE) && (cfg.role == XIF_ROLE_MASTER)) begin
      uvm_config_db#(virtual xif_if #(PD_T))::set(this, "driver", "vif", vif);
      uvm_config_db#(xif_cfg)::set(this, "driver", "cfg", cfg);
      driver = xif_driver #(PD_T)::type_id::create("driver", this);
      sequencer = xif_sequencer #(PD_T)::type_id::create("sequencer", this);
    end
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);

    monitor.ap.connect(ap);
    if ((driver != null) && (sequencer != null)) begin
      driver.seq_item_port.connect(sequencer.seq_item_export);
    end
  endfunction
endclass

`endif
