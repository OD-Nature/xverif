`ifndef XIF_ITEM_SVH
`define XIF_ITEM_SVH

class xif_item #(type PD_T = logic [31:0]) extends uvm_sequence_item;
  PD_T         pd;
  int unsigned leading_cycles;
  int unsigned post_cycles;

  `uvm_object_param_utils_begin(xif_item #(PD_T))
    `uvm_field_int(pd, UVM_DEFAULT)
    `uvm_field_int(leading_cycles, UVM_DEFAULT)
    `uvm_field_int(post_cycles, UVM_DEFAULT)
  `uvm_object_utils_end

  function new(string name = "xif_item");
    super.new(name);
    pd = '0;
    leading_cycles = 0;
    post_cycles = 0;
  endfunction

  function void do_print(uvm_printer printer);
    super.do_print(printer);
    printer.print_generic("pd", "struct", 0, $sformatf("%0p", this.pd));
  endfunction

  function void do_copy(uvm_object rhs);
    xif_item #(PD_T) rhs_item;

    super.do_copy(rhs);
    if (!$cast(rhs_item, rhs)) begin
      `uvm_fatal("XIF_COPY_CAST", "do_copy rhs is not an xif_item with matching PD_T")
    end

    pd = rhs_item.pd;
    leading_cycles = rhs_item.leading_cycles;
    post_cycles = rhs_item.post_cycles;
  endfunction

  function bit do_compare(uvm_object rhs, uvm_comparer comparer);
    xif_item #(PD_T) rhs_item;
    logic [$bits(PD_T)-1:0] lhs_pd_bits;
    logic [$bits(PD_T)-1:0] rhs_pd_bits;

    if (!$cast(rhs_item, rhs)) begin
      return 1'b0;
    end

    lhs_pd_bits = pd;
    rhs_pd_bits = rhs_item.pd;
    return super.do_compare(rhs, comparer) &&
           (lhs_pd_bits === rhs_pd_bits) &&
           (leading_cycles == rhs_item.leading_cycles) &&
           (post_cycles == rhs_item.post_cycles);
  endfunction

  function string convert2string();
    return $sformatf(
      "pd=%p leading_cycles=%0d post_cycles=%0d",
      pd,
      leading_cycles,
      post_cycles
    );
  endfunction
endclass

`endif
