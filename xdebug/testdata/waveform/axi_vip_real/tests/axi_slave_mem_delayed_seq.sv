`ifndef GUARD_AXI_SLAVE_MEM_DELAYED_SEQ_SV
`define GUARD_AXI_SLAVE_MEM_DELAYED_SEQ_SV

//=======================================================================
// AXI Slave Memory Sequence with Random Delays
// - Uses VIP built-in memory
// - Configures random delays (100-300 cycles) for responses
// - Initializes memory with random content
//=======================================================================

class axi_slave_mem_delayed_seq extends svt_axi_slave_base_sequence;

  `uvm_object_utils(axi_slave_mem_delayed_seq)

  // Delay configuration (in clock cycles)
  rand int min_resp_delay = 100;
  rand int max_resp_delay = 300;

  // Memory initialization
  rand bit init_mem_random = 1;
  rand bit [31:0] mem_start_addr = 32'h0;
  rand bit [31:0] mem_size = 32'h10000;  // 64KB

  // Statistics
  int num_wr_responses = 0;
  int num_rd_responses = 0;
  int total_bdelay = 0;
  int total_rdelay = 0;

  // Constraints
  constraint valid_delay_range {
    min_resp_delay >= 0;
    max_resp_delay >= min_resp_delay;
    max_resp_delay <= 1000;
  }

  // Constructor
  function new(string name="axi_slave_mem_delayed_seq");
    super.new(name);
  endfunction

  // Pre-body: Initialize memory with random content
  virtual task pre_body();
    bit [63:0] rand_data;
    bit [31:0] addr;

    super.pre_body();

    `uvm_info("SLAVE_SEQ", "=============================================", UVM_LOW)
    `uvm_info("SLAVE_SEQ", "Slave Memory Sequence Initializing...", UVM_LOW)
    `uvm_info("SLAVE_SEQ", $sformatf("Delay range: %0d - %0d cycles", min_resp_delay, max_resp_delay), UVM_LOW)

    // Get memory handle from base class
    instantiate_axi_slave_mem();

    if (axi_slave_mem != null && init_mem_random) begin
      `uvm_info("SLAVE_SEQ", "Initializing memory with random data...", UVM_MEDIUM)

      // Initialize memory with random data (8-byte words)
      for (int i = 0; i < mem_size/8; i++) begin
        addr = mem_start_addr + (i * 8);
        rand_data = {$urandom, $urandom};  // 64-bit random data
        axi_slave_mem.write(addr, rand_data, 8'hFF);
      end

      `uvm_info("SLAVE_SEQ", $sformatf("Memory initialized: 0x%0h - 0x%0h",
                mem_start_addr, mem_start_addr + mem_size), UVM_LOW)
    end
    else begin
      `uvm_info("SLAVE_SEQ", "Memory not initialized (null or disabled)", UVM_MEDIUM)
    end

    `uvm_info("SLAVE_SEQ", "=============================================", UVM_LOW)
  endtask

  // Main body: Respond to transactions with delays
  virtual task body();
    integer status;
    svt_configuration get_cfg;
    svt_axi_port_configuration cfg;
    int bvalid_delay_val;
    int rvalid_delay_val;
    int ai_complex_delay_mode = 0;
    int delay_profile;
    svt_axi_slave_transaction req_resp;
    bit is_write;
    bit is_read;

    `uvm_info("SLAVE_SEQ", "Slave sequence started - waiting for transactions...", UVM_MEDIUM)

    // Get configuration
    p_sequencer.get_cfg(get_cfg);
    if (!$cast(cfg, get_cfg)) begin
      `uvm_fatal("SLAVE_SEQ", "Unable to cast configuration to svt_axi_port_configuration")
    end
    void'($value$plusargs("ai_complex_delay_mode=%0d", ai_complex_delay_mode));

    // Consume responses from driver
    sink_responses();

    // Main loop: wait for requests and respond
    forever begin
      // Get request from sequencer
      p_sequencer.response_request_port.peek(req_resp);

      // Cycle through three fixed values and one fixed-seed random value.
      // This gives deterministic corner cases without losing delay diversity.
      delay_profile = (num_wr_responses + num_rd_responses) % 4;
      case (delay_profile)
        0: begin bvalid_delay_val = 0;  rvalid_delay_val = 0;  end
        1: begin bvalid_delay_val = 4;  rvalid_delay_val = 4;  end
        2: begin bvalid_delay_val = 17; rvalid_delay_val = 17; end
        default: begin
          bvalid_delay_val = $urandom_range(min_resp_delay, max_resp_delay);
          rvalid_delay_val = $urandom_range(min_resp_delay, max_resp_delay);
        end
      endcase
      if (ai_complex_delay_mode) begin
        if ((num_wr_responses % 9) == 0)
          bvalid_delay_val = 750;
        else if ((num_wr_responses % 4) == 0)
          bvalid_delay_val = 120;
        else
          bvalid_delay_val = 8 + (num_wr_responses % 5);

        if ((num_rd_responses % 7) == 0)
          rvalid_delay_val = 850;
        else if ((num_rd_responses % 3) == 0)
          rvalid_delay_val = 160;
        else
          rvalid_delay_val = 10 + (num_rd_responses % 7);
      end

      // Randomize response with delay constraints
      req_resp.set_cfg(cfg);
      status = req_resp.randomize with {
        // Write response delay
        bvalid_delay == bvalid_delay_val;

        // Read response delays (per beat)
        foreach (rvalid_delay[i]) {
          rvalid_delay[i] == rvalid_delay_val;
        }

        // Response status
        bresp == svt_axi_slave_transaction::OKAY;
        foreach (rresp[i]) {
          rresp[i] == svt_axi_slave_transaction::OKAY;
        }

        // Keep READY at zero delay so the write phase-order matrix is exact.
        addr_ready_delay == 0;
        foreach (wready_delay[i]) wready_delay[i] == 0;
      };

      if (!status)
        `uvm_fatal("SLAVE_SEQ", "Unable to randomize slave response")

      is_write = (req_resp.get_transmitted_channel() == svt_axi_transaction::WRITE);
      is_read = (req_resp.get_transmitted_channel() == svt_axi_transaction::READ);

      // Handle memory operations
      if (req_resp.get_transmitted_channel() == svt_axi_transaction::WRITE) begin
        put_write_transaction_data_to_mem(req_resp);
      end
      else if (req_resp.get_transmitted_channel() == svt_axi_transaction::READ) begin
        get_read_data_from_mem_to_transaction(req_resp);
      end

      // Send response to driver
      $cast(req, req_resp);
      `uvm_send(req)
      $display("AXI_RESPONSE_DELAY_JSON {\"profile\":%0d,\"channel\":\"%s\",\"bvalid_delay\":%0d,\"rvalid_delay\":%0d}",
               delay_profile, is_write ? "B" : "R",
               req_resp.bvalid_delay,
               req_resp.rvalid_delay.size() ? req_resp.rvalid_delay[0] : 0);

      if (is_write) begin
        num_wr_responses++;
        total_bdelay += req_resp.bvalid_delay;

        if (num_wr_responses % 100 == 0)
          `uvm_info("SLAVE_SEQ", $sformatf("Write responses: %0d", num_wr_responses), UVM_MEDIUM)
      end
      else if (is_read) begin
        num_rd_responses++;
        total_rdelay += req_resp.rvalid_delay[0];

        if (num_rd_responses % 100 == 0)
          `uvm_info("SLAVE_SEQ", $sformatf("Read responses: %0d", num_rd_responses), UVM_MEDIUM)
      end
    end
  endtask

  // Post-body: Report statistics
  virtual task post_body();
    real avg_bdelay, avg_rdelay;

    `uvm_info("SLAVE_SEQ", "=============================================", UVM_LOW)
    `uvm_info("SLAVE_SEQ", "SLAVE SEQUENCE STATISTICS", UVM_LOW)
    `uvm_info("SLAVE_SEQ", "=============================================", UVM_LOW)
    `uvm_info("SLAVE_SEQ", $sformatf("Write responses: %0d", num_wr_responses), UVM_LOW)
    `uvm_info("SLAVE_SEQ", $sformatf("Read responses:  %0d", num_rd_responses), UVM_LOW)

    if (num_wr_responses > 0) begin
      avg_bdelay = real'(total_bdelay) / num_wr_responses;
      `uvm_info("SLAVE_SEQ", $sformatf("Average BVALID delay: %0.2f cycles", avg_bdelay), UVM_LOW)
    end

    if (num_rd_responses > 0) begin
      avg_rdelay = real'(total_rdelay) / num_rd_responses;
      `uvm_info("SLAVE_SEQ", $sformatf("Average RVALID delay: %0.2f cycles", avg_rdelay), UVM_LOW)
    end

    `uvm_info("SLAVE_SEQ", "=============================================", UVM_LOW)
  endtask

endclass

`endif
