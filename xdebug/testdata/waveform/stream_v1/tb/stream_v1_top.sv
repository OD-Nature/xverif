`timescale 1ns/1ps

module stream_v1_top;
  localparam int N = 20000;

  reg clk;
  reg rst_n;

  reg        vo_vld;
  reg [31:0] vo_data;

  reg        ready_vld;
  reg        ready_flush;
  reg        ready_rdy;
  reg [31:0] ready_data;
  reg [15:0] ready_addr_hi;
  reg [15:0] ready_addr_lo;
  reg [1:0]  ready_cmd;
  reg [1:0]  ready_chid;

  reg        bp_vld;
  reg        bp_bp;
  reg [31:0] bp_data;

  reg        rpkt_vld;
  reg        rpkt_rdy;
  reg        rpkt_sop;
  reg        rpkt_eop;
  reg [7:0]  rpkt_opcode;
  reg [15:0] rpkt_seq;
  reg [31:0] rpkt_data;

  reg        bpkt_vld;
  reg        bpkt_bp;
  reg        bpkt_sop;
  reg        bpkt_eop;
  reg [7:0]  bpkt_badstable;
  reg [15:0] bpkt_seq;
  reg [31:0] bpkt_data;

  reg        npkt_vld;
  reg        npkt_rdy;
  reg        npkt_bp;
  reg        npkt_sop;
  reg        npkt_eop;
  reg [1:0]  npkt_chid;
  reg [15:0] npkt_seq;
  reg [31:0] npkt_data;

  reg        ipkt_vld;
  reg        ipkt_rdy;
  reg        ipkt_sop;
  reg        ipkt_eop;
  reg [1:0]  ipkt_chid;
  reg [15:0] ipkt_tag;
  reg [15:0] ipkt_seq;
  reg [31:0] ipkt_data;

  integer valid_only_count;
  integer ready_count;
  integer ready_stall_count;
  integer bp_count;
  integer bp_stall_count;
  integer ready_packet_count;
  integer ready_packet_packets;
  integer bp_packet_count;
  integer bp_packet_packets;
  integer negedge_count;
  integer negedge_packets;
  integer negedge_conflicts;
  integer interleaved_count;
  integer interleaved_packets;
  integer pos_done;
  integer neg_done;

  initial begin
    clk = 1'b0;
    forever #5 clk = ~clk;
  end

  initial begin
    $fsdbDumpfile("waves.fsdb");
    $fsdbDumpvars(0, stream_v1_top);
  end

  task init_signals;
    begin
      vo_vld = 1'b0;
      vo_data = 32'h0;
      ready_vld = 1'b0;
      ready_flush = 1'b0;
      ready_rdy = 1'b0;
      ready_data = 32'h0;
      ready_addr_hi = 16'h0;
      ready_addr_lo = 16'h0;
      ready_cmd = 2'b00;
      ready_chid = 2'b00;
      bp_vld = 1'b0;
      bp_bp = 1'b0;
      bp_data = 32'h0;
      rpkt_vld = 1'b0;
      rpkt_rdy = 1'b0;
      rpkt_sop = 1'b0;
      rpkt_eop = 1'b0;
      rpkt_opcode = 8'h0;
      rpkt_seq = 16'h0;
      rpkt_data = 32'h0;
      bpkt_vld = 1'b0;
      bpkt_bp = 1'b0;
      bpkt_sop = 1'b0;
      bpkt_eop = 1'b0;
      bpkt_badstable = 8'h0;
      bpkt_seq = 16'h0;
      bpkt_data = 32'h0;
      npkt_vld = 1'b0;
      npkt_rdy = 1'b0;
      npkt_bp = 1'b0;
      npkt_sop = 1'b0;
      npkt_eop = 1'b0;
      npkt_chid = 2'b00;
      npkt_seq = 16'h0;
      npkt_data = 32'h0;
      ipkt_vld = 1'b0;
      ipkt_rdy = 1'b0;
      ipkt_sop = 1'b0;
      ipkt_eop = 1'b0;
      ipkt_chid = 2'b00;
      ipkt_tag = 16'h0;
      ipkt_seq = 16'h0;
      ipkt_data = 32'h0;
    end
  endtask

  task write_expected;
    integer fd;
    begin
      fd = $fopen("stream_expected.json", "w");
      $fdisplay(fd, "{");
      $fdisplay(fd, "  \"streams\": {");
      $fdisplay(fd, "    \"valid_only\": {\"transfer_count\": %0d},", valid_only_count);
      $fdisplay(fd, "    \"ready_stream\": {\"transfer_count\": %0d, \"stall_cycles\": %0d},", ready_count, ready_stall_count);
      $fdisplay(fd, "    \"bp_stream\": {\"transfer_count\": %0d, \"stall_cycles\": %0d},", bp_count, bp_stall_count);
      $fdisplay(fd, "    \"ready_packet\": {\"transfer_count\": %0d, \"packet_count\": %0d},", ready_packet_count, ready_packet_packets);
      $fdisplay(fd, "    \"bp_packet\": {\"transfer_count\": %0d, \"packet_count\": %0d},", bp_packet_count, bp_packet_packets);
      $fdisplay(fd, "    \"ready_bp_packet_negedge\": {\"transfer_count\": %0d, \"packet_count\": %0d, \"ready_bp_conflict_count\": %0d},", negedge_count, negedge_packets, negedge_conflicts);
      $fdisplay(fd, "    \"interleaved_packet\": {\"transfer_count\": %0d, \"packet_count\": %0d}", interleaved_count, interleaved_packets);
      $fdisplay(fd, "  }");
      $fdisplay(fd, "}");
      $fclose(fd);
    end
  endtask

  initial begin
    rst_n = 1'b0;
    init_signals();
    valid_only_count = 0;
    ready_count = 0;
    ready_stall_count = 0;
    bp_count = 0;
    bp_stall_count = 0;
    ready_packet_count = 0;
    ready_packet_packets = 0;
    bp_packet_count = 0;
    bp_packet_packets = 0;
    negedge_count = 0;
    negedge_packets = 0;
    negedge_conflicts = 0;
    interleaved_count = 0;
    interleaved_packets = 0;
    pos_done = 0;
    neg_done = 0;

    repeat (5) @(posedge clk);
    @(negedge clk);
    rst_n = 1'b1;
  end

  initial begin : posedge_stream_drivers
    integer i;
    wait (rst_n === 1'b1);
    for (i = 0; i < N; i = i + 1) begin
      @(negedge clk);
      vo_vld = 1'b1;
      vo_data = 32'h10000000 + i;
      valid_only_count = valid_only_count + 1;

      ready_vld = 1'b1;
      ready_flush = ((i % 17) == 0);
      ready_rdy = ((i % 5) != 0);
      ready_data = 32'h20000000 + i;
      ready_addr_hi = 16'h4000 + i[15:0];
      ready_addr_lo = 16'h0100 + i[15:0];
      ready_cmd = (i[0] == 1'b0) ? 2'b01 : 2'b10;
      ready_chid = i[1:0];
      if (!ready_flush && ready_rdy) ready_count = ready_count + 1;
      if (!ready_flush && !ready_rdy) ready_stall_count = ready_stall_count + 1;

      bp_vld = 1'b1;
      bp_bp = ((i % 7) == 0);
      bp_data = 32'h30000000 + i;
      if (!bp_bp) bp_count = bp_count + 1;
      if (bp_bp) bp_stall_count = bp_stall_count + 1;

      rpkt_vld = 1'b1;
      rpkt_rdy = 1'b1;
      rpkt_sop = ((i % 4) == 0);
      rpkt_eop = ((i % 4) == 3);
      rpkt_opcode = 8'ha0 + ((i / 4) % 16);
      rpkt_seq = i[15:0];
      rpkt_data = 32'h40000000 + i;
      ready_packet_count = ready_packet_count + 1;
      if ((i % 4) == 3) ready_packet_packets = ready_packet_packets + 1;

      bpkt_vld = 1'b1;
      bpkt_bp = 1'b0;
      bpkt_sop = ((i % 4) == 0);
      bpkt_eop = ((i % 4) == 3);
      bpkt_badstable = i[7:0];
      bpkt_seq = i[15:0];
      bpkt_data = 32'h50000000 + i;
      bp_packet_count = bp_packet_count + 1;
      if ((i % 4) == 3) bp_packet_packets = bp_packet_packets + 1;

      ipkt_vld = 1'b1;
      ipkt_rdy = 1'b1;
      ipkt_chid = i[0];
      ipkt_sop = (((i / 2) % 4) == 0);
      ipkt_eop = (((i / 2) % 4) == 3);
      ipkt_tag = 16'h9000 + (i / 8);
      ipkt_seq = i[15:0];
      ipkt_data = 32'h70000000 + i;
      interleaved_count = interleaved_count + 1;
      if (((i / 2) % 4) == 3) interleaved_packets = interleaved_packets + 1;
    end

    @(negedge clk);
    vo_vld = 1'b0;
    ready_vld = 1'b0;
    bp_vld = 1'b0;
    rpkt_vld = 1'b0;
    bpkt_vld = 1'b0;
    ipkt_vld = 1'b0;
    pos_done = 1;
  end

  initial begin : negedge_stream_driver
    integer i;
    wait (rst_n === 1'b1);
    for (i = 0; i < N; i = i + 1) begin
      @(posedge clk);
      npkt_vld = 1'b1;
      npkt_rdy = 1'b1;
      npkt_bp = 1'b0;
      npkt_sop = ((i % 4) == 0);
      npkt_eop = ((i % 4) == 3);
      npkt_chid = (i / 4) % 4;
      npkt_seq = i[15:0];
      npkt_data = 32'h60000000 + i;
      negedge_count = negedge_count + 1;
      if ((i % 4) == 3) negedge_packets = negedge_packets + 1;
    end

    @(posedge clk);
    npkt_vld = 1'b1;
    npkt_rdy = 1'b1;
    npkt_bp = 1'b1;
    npkt_sop = 1'b0;
    npkt_eop = 1'b0;
    npkt_data = 32'h6bad0000;
    negedge_conflicts = negedge_conflicts + 1;

    @(posedge clk);
    npkt_vld = 1'b0;
    npkt_bp = 1'b0;
    neg_done = 1;
  end

  initial begin
    wait (pos_done && neg_done);
    repeat (4) @(posedge clk);
    write_expected();
    $finish;
  end
endmodule
