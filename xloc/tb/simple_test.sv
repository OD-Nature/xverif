// Called from xloc_tb — demonstrates multi-file coverage
task automatic simple_test();
  `uvm_error("PKT_MISMATCH", "expected=8'hFF actual=8'hFE")
  `uvm_error("PKT_MISMATCH", "expected=8'hAA actual=8'hBB")  // same file, different line -> same loc_id
  `uvm_warning("BAD_PKT", "packet with invalid header")
  `uvm_info("SIMPLE_TEST", "simple test finished", UVM_MEDIUM)
endtask
