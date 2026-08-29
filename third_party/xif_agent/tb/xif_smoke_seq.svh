`ifndef XIF_SMOKE_SEQ_SVH
`define XIF_SMOKE_SEQ_SVH

class xif_smoke_seq extends uvm_sequence #(xif_item #(xif_pd_t));
  rand int unsigned num_items;

  `uvm_object_utils(xif_smoke_seq)

  function new(string name = "xif_smoke_seq");
    super.new(name);
    num_items = 3;
  endfunction

  task body();
    xif_item #(xif_pd_t) req;
    int unsigned idx;

    for (idx = 0; idx < num_items; idx++) begin
      xif_pd_t payload;
      payload.opcode = 8'h10 + idx[7:0];
      payload.data   = 16'h1000 + idx[15:0];

      req = xif_item #(xif_pd_t)::type_id::create($sformatf("req_%0d", idx));
      req.pd = payload;
      req.leading_cycles = (idx % 3);
      req.post_cycles = ((idx + 1) % 2);

      `uvm_info("XIF_SEQ_SEND", $sformatf("sequence sending item %s", req.convert2string()), UVM_MEDIUM)
      start_item(req);
      finish_item(req);
    end
  endtask
endclass

`endif
