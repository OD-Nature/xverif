`timescale 1ns/1ps

module rc_arrays_tb;
  typedef struct packed {
    logic [7:0] opcode;
    logic [3:0] flags;
  } header_t;
  typedef struct packed {
    header_t header;
    logic [1:0][7:0] lanes;
  } packet_t;
  typedef struct {
    logic [7:0] tag;
    logic [15:0] words [0:1];
  } loose_t;
  typedef enum logic [2:0] {
    IDLE = 3'b001,
    BUSY = 3'b011,
    DONE = 3'b110
  } state_t;
  typedef struct packed {
    state_t state;
    logic flag;
  } enum_packet_t;

  packet_t packets [0:1];
  packet_t [1:0] packed_packets;
  packet_t matrix [0:1][0:1];
  loose_t loose [0:1];
  state_t enum_state;
  enum_packet_t enum_packet;
  enum_packet_t enum_packets [0:1];
  state_t enum_states [0:1];
  logic enum_state_bit;
  logic [1:0] enum_state_slice;

  assign enum_state_bit = enum_state[0];
  assign enum_state_slice = enum_state[1:0];

  task automatic set_values(input logic [7:0] base);
    for (int i = 0; i < 2; ++i) begin
      packets[i].header.opcode = base + i;
      packets[i].header.flags = 4'ha;
      packets[i].lanes[0] = base + i + 2;
      packets[i].lanes[1] = base + i + 3;
      packed_packets[i] = packets[i];
      loose[i].tag = base + i;
      loose[i].words[0] = 16'h1200 + base + i;
      loose[i].words[1] = 16'h3400 + base + i;
      for (int j = 0; j < 2; ++j) begin
        matrix[i][j] = packets[i];
        matrix[i][j].header.opcode = base + i + j;
      end
    end
  endtask

  initial begin
    $fsdbDumpfile("waves.fsdb");
    $fsdbDumpvars(0, rc_arrays_tb, "+all");
    $fsdbDumpMDA(0, rc_arrays_tb);
    set_values(8'h21);
    enum_state = IDLE;
    enum_packet = '{state: BUSY, flag: 1'b1};
    enum_packets[0] = '{state: IDLE, flag: 1'b0};
    enum_packets[1] = '{state: DONE, flag: 1'b1};
    enum_states[0] = BUSY;
    enum_states[1] = DONE;
    #10ns;
    set_values(8'h52);
    enum_state = DONE;
    enum_packet = '{state: IDLE, flag: 1'b0};
    enum_packets[0] = '{state: BUSY, flag: 1'b1};
    enum_packets[1] = '{state: IDLE, flag: 1'b0};
    enum_states[0] = DONE;
    enum_states[1] = BUSY;
    #10ns;
    $display("RC_ARRAYS_PASS");
    $finish;
  end
endmodule
