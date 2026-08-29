`ifndef GUARD_AXI_MULTI_ID_WR_RD_SEQ_SV
`define GUARD_AXI_MULTI_ID_WR_RD_SEQ_SV

//=======================================================================
// AXI Multi-ID Write/Read Sequence
// Sends transactions with different IDs, mix of single-beat and burst
//=======================================================================

//-----------------------------------------------------------------------
// Multi-ID Master Sequence
// Each ID sends N write + N read transactions
//-----------------------------------------------------------------------
class axi_multi_id_master_seq extends svt_axi_master_base_sequence;

  `uvm_object_utils(axi_multi_id_master_seq)

  // Sequence configuration
  rand int num_ids = 4;                     // Number of different IDs to use
  rand int trans_per_id = 200;              // Read/Write count per ID
  rand int outstanding_depth = 16;          // Per-ID, per-direction outstanding depth
  rand bit [31:0] mem_start_addr = 32'h0;   // Memory start address
  rand bit [31:0] mem_size = 32'h10000;     // Memory size (64KB)

  // Percentage of single-beat transactions (rest are bursts)
  rand int single_beat_pct = 30;

  // Burst length range for non-single-beat
  rand int min_burst_len = 2;
  rand int max_burst_len = 16;

  // Every four writes cover AW-before-W, W-before-AW, same-cycle and
  // fixed-seed randomized ordering.  The simulator seed makes profile 3
  // deterministic across fixture rebuilds.
  int write_order_profile_count[4];
  string axi_profile = "stress";

  // Track statistics
  int total_writes = 0;
  int total_reads = 0;
  int id_writes[int];
  int id_reads[int];

  // Constraints
  constraint valid_num_ids {
    num_ids inside {[1:16]};
  }

  constraint valid_trans_count {
    trans_per_id inside {[1:10000]};
  }

  constraint valid_outstanding_depth {
    outstanding_depth inside {[1:32]};
  }

  constraint valid_burst_range {
    min_burst_len >= 2;
    max_burst_len <= 256;
    min_burst_len <= max_burst_len;
  }

  // Constructor
  function new(string name="axi_multi_id_master_seq");
    super.new(name);
  endfunction

  // Pre-body - raise objection and initialize
  virtual task pre_body();
    super.pre_body();

    if (cfg == null) begin
      `uvm_fatal("SEQ", "Master sequence did not receive a valid AXI port configuration")
    end
    void'($value$plusargs("axi_profile=%s", axi_profile));

    // Raise objection if starting phase is set
    if (starting_phase != null) begin
      starting_phase.raise_objection(this, "axi_multi_id_master_seq starting");
      `uvm_info("SEQ", "Objection raised", UVM_MEDIUM)
    end

    `uvm_info("SEQ", $sformatf("Multi-ID Sequence Configuration:"), UVM_LOW)
    `uvm_info("SEQ", $sformatf("  Number of IDs: %0d", num_ids), UVM_LOW)
    `uvm_info("SEQ", $sformatf("  Transactions per ID: %0d reads + %0d writes", trans_per_id, trans_per_id), UVM_LOW)
    `uvm_info("SEQ", $sformatf("  Outstanding depth per ID/direction: %0d", outstanding_depth), UVM_LOW)
    `uvm_info("SEQ", $sformatf("  Memory Range: 0x%0h - 0x%0h", mem_start_addr, mem_start_addr + mem_size), UVM_LOW)
    `uvm_info("SEQ", $sformatf("  Single-beat percentage: %0d%%", single_beat_pct), UVM_LOW)
    `uvm_info("SEQ", $sformatf("  AXI delay profile: %s", axi_profile), UVM_LOW)
  endtask

  // Task: Send write transactions for a specific ID
  virtual task send_write_transactions(int id);
    bit [31:0] addr;
    int burst_len;
    bit is_single_beat;
    integer status;
    int max_burst_for_4k;
    svt_axi_master_transaction xact;
    int issued = 0;
    int completed = 0;
    int in_flight = 0;
    int order_profile;

    `uvm_info("SEQ", $sformatf("Starting WRITE for ID=%0d (%0d transactions)...", id, trans_per_id), UVM_MEDIUM)

    while (completed < trans_per_id) begin
      while (issued < trans_per_id && in_flight < outstanding_depth) begin
      // Determine if this is a single-beat transaction
      is_single_beat = ($urandom_range(1, 100) <= single_beat_pct);

      // Randomize burst length
      if (is_single_beat)
        burst_len = 1;
      else
        burst_len = $urandom_range(min_burst_len, max_burst_len);

      // Calculate address (aligned to data width)
      addr = mem_start_addr + ($urandom_range(0, mem_size/8 - 1) * 8);

      // Ensure burst does not cross 4KB boundary (AXI protocol requirement)
      max_burst_for_4k = (4096 - (addr % 4096)) / 8;
      if (burst_len > max_burst_for_4k)
        burst_len = max_burst_for_4k;
      if (burst_len < 1)
        burst_len = 1;

      // Ensure burst doesn't exceed memory
      if (addr + (burst_len * 8) > mem_start_addr + mem_size)
        addr = mem_start_addr;

      xact = svt_axi_master_transaction::type_id::create($sformatf("write_xact_%0d_%0d", id, issued));
      xact.set_cfg(cfg);
      order_profile = (issued + id) % 4;
      status = xact.randomize() with {
        xact_type == svt_axi_transaction::WRITE;
        id == local::id;
        addr == local::addr;
        burst_length == local::burst_len;
        burst_type == svt_axi_transaction::INCR;
        burst_size == svt_axi_transaction::BURST_SIZE_64BIT;
        cache_type == 4'b0011;  // Normal, non-cacheable, bufferable
        // Explicitly size dynamic arrays for O-2018.09 VIP
        data.size() == local::burst_len;
        wstrb.size() == local::burst_len;
        wvalid_delay.size() == local::burst_len;
        foreach (wstrb[j]) { wstrb[j] == 8'hFF; }
        if (local::order_profile == 0) {
          // Address handshake, then first write-data handshake four cycles later.
          data_before_addr == 0;
          addr_valid_delay == 0;
          reference_event_for_first_wvalid_delay == svt_axi_transaction::WRITE_ADDR_HANDSHAKE;
          wvalid_delay[0] == 4;
          foreach (wvalid_delay[j]) if (j > 0) wvalid_delay[j] == 0;
        }
        else if (local::order_profile == 1) {
          // First write data is accepted four cycles before the address phase.
          data_before_addr == 1;
          reference_event_for_first_wvalid_delay == svt_axi_transaction::PREV_WRITE_DATA_HANDSHAKE;
          wvalid_delay[0] == 0;
          reference_event_for_addr_valid_delay == svt_axi_transaction::FIRST_WVALID_DATA_BEFORE_ADDR;
          addr_valid_delay == 4;
          foreach (wvalid_delay[j]) if (j > 0) wvalid_delay[j] == 0;
        }
        else if (local::order_profile == 2) {
          // AWVALID and WVALID start together; zero-ready delay makes both handshake.
          data_before_addr == 0;
          addr_valid_delay == 0;
          reference_event_for_first_wvalid_delay == svt_axi_transaction::WRITE_ADDR_VALID;
          wvalid_delay[0] == 0;
          foreach (wvalid_delay[j]) if (j > 0) wvalid_delay[j] == 0;
        }
        else {
          // Fixed-seed random delay profile. Keep reference events consistent
          // with the selected direction so the result is legal AXI stimulus.
          data_before_addr dist {0 := 1, 1 := 1};
          if (data_before_addr) {
            reference_event_for_first_wvalid_delay == svt_axi_transaction::PREV_WRITE_DATA_HANDSHAKE;
            reference_event_for_addr_valid_delay inside {
              svt_axi_transaction::FIRST_WVALID_DATA_BEFORE_ADDR,
              svt_axi_transaction::FIRST_DATA_HANDSHAKE_DATA_BEFORE_ADDR
            };
          }
          else {
            reference_event_for_first_wvalid_delay inside {
              svt_axi_transaction::WRITE_ADDR_VALID,
              svt_axi_transaction::WRITE_ADDR_HANDSHAKE
            };
          }
          addr_valid_delay inside {[0:7]};
          foreach (wvalid_delay[j]) wvalid_delay[j] inside {[0:7]};
        }
      };

      if (!status) begin
        `uvm_fatal("SEQ", $sformatf("Randomization failed for WRITE id=%0d addr=0x%0h len=%0d", id, addr, burst_len))
      end

      `uvm_send(xact)
      write_order_profile_count[order_profile]++;
      $display("AXI_DELAY_PROFILE_JSON {\"id\":%0d,\"issued\":%0d,\"profile\":%0d,\"data_before_addr\":%0d,\"addr_valid_delay\":%0d,\"first_wvalid_delay\":%0d}",
               id, issued, order_profile, xact.data_before_addr,
               xact.addr_valid_delay, xact.wvalid_delay[0]);
      issued++;
      in_flight++;

      fork
        begin
          automatic svt_axi_master_transaction wait_xact = xact;
          wait_xact.wait_for_transaction_end();
          completed++;
          in_flight--;
          total_writes++;
          id_writes[id]++;

          if (completed % 100 == 0 || completed == trans_per_id)
            `uvm_info("SEQ", $sformatf("ID=%0d WRITE progress: %0d/%0d", id, completed, trans_per_id), UVM_MEDIUM)
        end
      join_none
      end

      if (completed < trans_per_id) begin
        if (issued < trans_per_id)
          wait (in_flight < outstanding_depth || completed >= trans_per_id);
        else
          wait (completed >= trans_per_id);
      end
    end

    wait fork;
    `uvm_info("SEQ", $sformatf("ID=%0d WRITE completed", id), UVM_MEDIUM)
  endtask

  // Task: Send read transactions for a specific ID
  virtual task send_read_transactions(int id);
    bit [31:0] addr;
    int burst_len;
    bit is_single_beat;
    integer status;
    int max_burst_for_4k;
    svt_axi_master_transaction xact;
    int issued = 0;
    int completed = 0;
    int in_flight = 0;

    `uvm_info("SEQ", $sformatf("Starting READ for ID=%0d (%0d transactions)...", id, trans_per_id), UVM_MEDIUM)

    while (completed < trans_per_id) begin
      while (issued < trans_per_id && in_flight < outstanding_depth) begin
      // Determine if this is a single-beat transaction
      is_single_beat = ($urandom_range(1, 100) <= single_beat_pct);

      // Randomize burst length
      if (is_single_beat)
        burst_len = 1;
      else
        burst_len = $urandom_range(min_burst_len, max_burst_len);

      // Calculate address (can be same as written or random)
      addr = mem_start_addr + ($urandom_range(0, mem_size/8 - 1) * 8);

      // Ensure burst does not cross 4KB boundary (AXI protocol requirement)
      max_burst_for_4k = (4096 - (addr % 4096)) / 8;
      if (burst_len > max_burst_for_4k)
        burst_len = max_burst_for_4k;
      if (burst_len < 1)
        burst_len = 1;

      // Ensure burst doesn't exceed memory
      if (addr + (burst_len * 8) > mem_start_addr + mem_size)
        addr = mem_start_addr;

      xact = svt_axi_master_transaction::type_id::create($sformatf("read_xact_%0d_%0d", id, issued));
      xact.set_cfg(cfg);
      status = xact.randomize() with {
        xact_type == svt_axi_transaction::READ;
        id == local::id;
        addr == local::addr;
        burst_length == local::burst_len;
        burst_type == svt_axi_transaction::INCR;
        burst_size == svt_axi_transaction::BURST_SIZE_64BIT;
        cache_type == 4'b0011;
        // Explicitly size dynamic arrays for O-2018.09 VIP
        data.size() == local::burst_len;
        rresp.size() == local::burst_len;
        rready_delay.size() == local::burst_len;
        addr_valid_delay inside {[0:7]};
        foreach (rready_delay[j]) rready_delay[j] == 0;
      };

      if (!status) begin
        `uvm_fatal("SEQ", $sformatf("Randomization failed for READ id=%0d addr=0x%0h len=%0d", id, addr, burst_len))
      end

      `uvm_send(xact)
      issued++;
      in_flight++;

      fork
        begin
          automatic svt_axi_master_transaction wait_xact = xact;
          wait_xact.wait_for_transaction_end();
          completed++;
          in_flight--;
          total_reads++;
          id_reads[id]++;

          if (completed % 100 == 0 || completed == trans_per_id)
            `uvm_info("SEQ", $sformatf("ID=%0d READ progress: %0d/%0d", id, completed, trans_per_id), UVM_MEDIUM)
        end
      join_none
      end

      if (completed < trans_per_id) begin
        if (issued < trans_per_id)
          wait (in_flight < outstanding_depth || completed >= trans_per_id);
        else
          wait (completed >= trans_per_id);
      end
    end

    wait fork;
    `uvm_info("SEQ", $sformatf("ID=%0d READ completed", id), UVM_MEDIUM)
  endtask

  // Main body - Parallel read and write for each ID
  virtual task body();
    `uvm_info("SEQ", "=============================================", UVM_LOW)
    `uvm_info("SEQ", "STARTING PARALLEL READ/WRITE TRANSACTIONS", UVM_LOW)
    `uvm_info("SEQ", "=============================================", UVM_LOW)

    // Use fork-join to run all ID transactions in parallel
    // Each ID runs writes and reads in parallel
    for (int id = 0; id < num_ids; id++) begin
      automatic int current_id = id;
      fork
        begin
          // Each ID: run writes and reads in parallel
          fork
            send_write_transactions(current_id);
            send_read_transactions(current_id);
          join
        end
      join_none
    end

    // Wait for all forked processes to complete
    wait fork;

    // Report statistics
    `uvm_info("SEQ", "=============================================", UVM_LOW)
    `uvm_info("SEQ", "SEQUENCE STATISTICS", UVM_LOW)
    `uvm_info("SEQ", "=============================================", UVM_LOW)
    `uvm_info("SEQ", $sformatf("Total WRITE transactions: %0d", total_writes), UVM_LOW)
    `uvm_info("SEQ", $sformatf("Total READ transactions:  %0d", total_reads), UVM_LOW)

    foreach (id_writes[id]) begin
      `uvm_info("SEQ", $sformatf("ID=%0d: Writes=%0d, Reads=%0d", id, id_writes[id], id_reads[id]), UVM_LOW)
    end
    `uvm_info("SEQ", $sformatf("Write order profiles: AW_FIRST=%0d W_FIRST=%0d SAME_CYCLE=%0d FIXED_SEED_RANDOM=%0d",
              write_order_profile_count[0], write_order_profile_count[1],
              write_order_profile_count[2], write_order_profile_count[3]), UVM_LOW)
    `uvm_info("SEQ", "=============================================", UVM_LOW)

  endtask

  // Post-body - drop objection
  virtual task post_body();
    super.post_body();

    // Drop objection if starting phase is set
    if (starting_phase != null) begin
      starting_phase.drop_objection(this, "axi_multi_id_master_seq completed");
      `uvm_info("SEQ", "Objection dropped", UVM_MEDIUM)
    end
  endtask

endclass

`endif
