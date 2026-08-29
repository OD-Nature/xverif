`ifndef XIF_LINK_WRAPPERS_SV
`define XIF_LINK_WRAPPERS_SV

module xif_pair_link_wrapper #(type PD_T = logic [31:0]) (
  input  logic master_vld_i,
  input  PD_T  master_pd_i,
  input  logic slave_rdy_i,
  input  logic slave_bp_i,
  output logic slave_vld_o,
  output PD_T  slave_pd_o,
  output logic master_rdy_o,
  output logic master_bp_o
);
  assign slave_vld_o  = master_vld_i;
  assign slave_pd_o   = master_pd_i;
  assign master_rdy_o = slave_rdy_i;
  assign master_bp_o  = slave_bp_i;
endmodule

module xif_observe_link_wrapper #(type PD_T = logic [31:0]) (
  input  logic src_vld_i,
  input  PD_T  src_pd_i,
  input  logic src_rdy_i,
  output logic dst_vld_o,
  output PD_T  dst_pd_o,
  output logic dst_rdy_o
);
  assign dst_vld_o = src_vld_i;
  assign dst_pd_o  = src_pd_i;
  assign dst_rdy_o = src_rdy_i;
endmodule

`endif
