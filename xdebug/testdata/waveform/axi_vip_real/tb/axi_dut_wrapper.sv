`timescale 1ns/1ps

// Pin-level AXI4 bridge between the active SVT master and slave agents.
// SVT interface signals have internal procedural drivers, so the bridge uses
// force connections instead of continuous assignments to avoid multi-driver
// conflicts. The slave agent owns all memory and response behavior.
module axi_dut_wrapper (
  input logic clk,
  input logic rst_n,
  svt_axi_if axi_if
);
  initial force axi_if.slave_if[0].awvalid  = axi_if.master_if[0].awvalid;
  initial force axi_if.slave_if[0].awid     = axi_if.master_if[0].awid;
  initial force axi_if.slave_if[0].awaddr   = axi_if.master_if[0].awaddr;
  initial force axi_if.slave_if[0].awlen    = axi_if.master_if[0].awlen;
  initial force axi_if.slave_if[0].awsize   = axi_if.master_if[0].awsize;
  initial force axi_if.slave_if[0].awburst  = axi_if.master_if[0].awburst;
  initial force axi_if.slave_if[0].awlock   = axi_if.master_if[0].awlock;
  initial force axi_if.slave_if[0].awcache  = axi_if.master_if[0].awcache;
  initial force axi_if.slave_if[0].awprot   = axi_if.master_if[0].awprot;
  initial force axi_if.slave_if[0].awqos    = axi_if.master_if[0].awqos;
  initial force axi_if.slave_if[0].awregion = axi_if.master_if[0].awregion;
  initial force axi_if.slave_if[0].awuser   = axi_if.master_if[0].awuser;
  initial force axi_if.master_if[0].awready = axi_if.slave_if[0].awready;

  initial force axi_if.slave_if[0].wvalid  = axi_if.master_if[0].wvalid;
  initial force axi_if.slave_if[0].wid     = axi_if.master_if[0].wid;
  initial force axi_if.slave_if[0].wdata   = axi_if.master_if[0].wdata;
  initial force axi_if.slave_if[0].wstrb   = axi_if.master_if[0].wstrb;
  initial force axi_if.slave_if[0].wlast   = axi_if.master_if[0].wlast;
  initial force axi_if.slave_if[0].wuser   = axi_if.master_if[0].wuser;
  initial force axi_if.master_if[0].wready = axi_if.slave_if[0].wready;

  initial force axi_if.master_if[0].bvalid = axi_if.slave_if[0].bvalid;
  initial force axi_if.master_if[0].bid    = axi_if.slave_if[0].bid;
  initial force axi_if.master_if[0].bresp  = axi_if.slave_if[0].bresp;
  initial force axi_if.master_if[0].buser  = axi_if.slave_if[0].buser;
  initial force axi_if.slave_if[0].bready  = axi_if.master_if[0].bready;

  initial force axi_if.slave_if[0].arvalid  = axi_if.master_if[0].arvalid;
  initial force axi_if.slave_if[0].arid     = axi_if.master_if[0].arid;
  initial force axi_if.slave_if[0].araddr   = axi_if.master_if[0].araddr;
  initial force axi_if.slave_if[0].arlen    = axi_if.master_if[0].arlen;
  initial force axi_if.slave_if[0].arsize   = axi_if.master_if[0].arsize;
  initial force axi_if.slave_if[0].arburst  = axi_if.master_if[0].arburst;
  initial force axi_if.slave_if[0].arlock   = axi_if.master_if[0].arlock;
  initial force axi_if.slave_if[0].arcache  = axi_if.master_if[0].arcache;
  initial force axi_if.slave_if[0].arprot   = axi_if.master_if[0].arprot;
  initial force axi_if.slave_if[0].arqos    = axi_if.master_if[0].arqos;
  initial force axi_if.slave_if[0].arregion = axi_if.master_if[0].arregion;
  initial force axi_if.slave_if[0].aruser   = axi_if.master_if[0].aruser;
  initial force axi_if.master_if[0].arready = axi_if.slave_if[0].arready;

  initial force axi_if.master_if[0].rvalid = axi_if.slave_if[0].rvalid;
  initial force axi_if.master_if[0].rid    = axi_if.slave_if[0].rid;
  initial force axi_if.master_if[0].rdata  = axi_if.slave_if[0].rdata;
  initial force axi_if.master_if[0].rresp  = axi_if.slave_if[0].rresp;
  initial force axi_if.master_if[0].rlast  = axi_if.slave_if[0].rlast;
  initial force axi_if.master_if[0].ruser  = axi_if.slave_if[0].ruser;
  initial force axi_if.slave_if[0].rready  = axi_if.master_if[0].rready;
endmodule
