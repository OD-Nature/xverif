`ifndef XIF_DRIVER_SVH
`define XIF_DRIVER_SVH

class xif_driver #(type PD_T = logic [31:0]) extends uvm_driver #(xif_item #(PD_T));
  typedef enum int unsigned {
    DRV_IDLE,
    DRV_LEADING,
    DRV_DRIVING,
    DRV_POST
  } drv_state_e;

  `uvm_component_param_utils(xif_driver #(PD_T))

  virtual xif_if #(PD_T) vif;
  xif_cfg                cfg;

  mailbox #(xif_item #(PD_T)) pending_items;

  function new(string name = "xif_driver", uvm_component parent = null);
    super.new(name, parent);
    pending_items = new(100);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);

    if (!uvm_config_db#(virtual xif_if #(PD_T))::get(this, "", "vif", vif)) begin
      `uvm_fatal("NOVIF", "xif_driver requires a virtual interface")
    end

    if (!uvm_config_db#(xif_cfg)::get(this, "", "cfg", cfg)) begin
      `uvm_fatal("NOCFG", "xif_driver requires xif_cfg")
    end

    cfg.sanitize();
  endfunction

  function automatic bit handshake_complete();
    return xif_handshake(1'b1, vif.drv_cb.rdy, vif.drv_cb.bp, cfg.flow_ctrl);
  endfunction

  function automatic PD_T build_idle_pd();
    logic [$bits(PD_T)-1:0] bits;

    case (cfg.idle_pd_policy)
      XIF_IDLE_X_ONLY: begin
        bits = 'x;
        return PD_T'(bits);
      end
      XIF_IDLE_FULL_RANDOM: begin
        case ($urandom_range(0, 3))
          0: bits = '0;
          1: bits = '1;
          2: bits = 'x;
          default: bits = 'z;
        endcase
        return PD_T'(bits);
      end
      default: begin
        return vif.pd;
      end
    endcase
  endfunction

  task automatic drive_idle_cycle();
    vif.drv_cb.vld <= 1'b0;
    if (cfg.idle_pd_policy != XIF_IDLE_STABLE) begin
      vif.drv_cb.pd <= build_idle_pd();
    end
  endtask

  task automatic drive_active_cycle(xif_item #(PD_T) item, output bit completed);
    completed = 1'b1;
    vif.drv_cb.vld <= 1'b1;
    vif.drv_cb.pd <= item.pd;
    @vif.drv_cb;

    if (!vif.drv_cb.rst_n) begin
      reset_driver();
      completed = 1'b0;
      return;
    end
  endtask

  task automatic reset_driver();
    vif.drv_cb.vld <= 1'b0;
    if (cfg.idle_pd_policy != XIF_IDLE_STABLE) begin
      vif.drv_cb.pd <= build_idle_pd();
    end
  endtask

  task automatic drive_idle_cycles(input int unsigned cycles, output bit completed);
    completed = 1'b1;
    repeat (cycles) begin
      if (!vif.drv_cb.rst_n) begin
        reset_driver();
        completed = 1'b0;
        return;
      end

      drive_idle_cycle();
      @vif.drv_cb;

      if (!vif.drv_cb.rst_n) begin
        reset_driver();
        completed = 1'b0;
        return;
      end
    end
  endtask

  task automatic fetch_sequence_items();
    xif_item #(PD_T) req;
    xif_item #(PD_T) req_clone;

    forever begin
      wait (vif.rst_n === 1'b1);
      seq_item_port.get_next_item(req);
      $cast(req_clone, req.clone());
      pending_items.put(req_clone);
      `uvm_info("XIF_DRV_GET", $sformatf("driver accepted item %s", req.convert2string()), UVM_MEDIUM)
      seq_item_port.item_done();
    end
  endtask

  task automatic drive_pending_items();
    xif_item #(PD_T) req;
    bit idle_done;
    bit active_done;
    bit transfer_done;
    int unsigned post_cycles;

    @vif.drv_cb;
    reset_driver();
    forever begin
      if (!vif.drv_cb.rst_n) begin
        reset_driver();
        @vif.drv_cb;
        continue;
      end

      req = null;
      if (!pending_items.try_get(req)) begin
        drive_idle_cycle();
        @vif.drv_cb;
        continue;
      end

      drive_idle_cycles(req.leading_cycles, idle_done);
      if (!idle_done) begin
        continue;
      end

      drive_active_cycle(req, active_done);
      if (!active_done) begin
        continue;
      end

      transfer_done = 1'b0;
      while (!transfer_done) begin
        if (!vif.drv_cb.rst_n) begin
          reset_driver();
          req = null;
          transfer_done = 1'b1;
          break;
        end

        if (handshake_complete()) begin
          post_cycles = req.post_cycles;
          `uvm_info("XIF_DRV_DONE", $sformatf("driver completed item %s", req.convert2string()), UVM_MEDIUM)
          req = null;
          drive_idle_cycles(post_cycles, idle_done);
          transfer_done = 1'b1;
          break;
        end

        drive_active_cycle(req, active_done);
        if (!active_done) begin
          req = null;
          transfer_done = 1'b1;
          break;
        end
      end
    end
  endtask

  task run_phase(uvm_phase phase);
    fork
      fetch_sequence_items();
      drive_pending_items();
    join
  endtask
endclass

`endif
