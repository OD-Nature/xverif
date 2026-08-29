`ifndef XIF_DUPLICATE_PD_SEQ_SVH
`define XIF_DUPLICATE_PD_SEQ_SVH

class xif_duplicate_pd_seq extends uvm_sequence #(xif_item #(xif_pd_t));
  rand int unsigned num_items;

  `uvm_object_utils(xif_duplicate_pd_seq)

  function new(string name = "xif_duplicate_pd_seq");
    super.new(name);
    num_items = 2;
  endfunction

  task body();
    xif_item #(xif_pd_t) req;
    xif_pd_t payload;
    int unsigned idx;

    payload.opcode = 8'h5a;
    payload.data = 16'ha55a;

    for (idx = 0; idx < num_items; idx++) begin
      req = xif_item #(xif_pd_t)::type_id::create($sformatf("dup_req_%0d", idx));
      req.pd = payload;
      req.leading_cycles = 0;
      req.post_cycles = 1;

      `uvm_info("XIF_SEQ_SEND", $sformatf("sequence sending duplicate item %s", req.convert2string()), UVM_MEDIUM)
      start_item(req);
      finish_item(req);
    end
  endtask
endclass

`endif
