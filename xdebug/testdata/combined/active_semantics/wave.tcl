call {$fsdbDumpvars(0,"active_semantics_tb.u_dut","+all")}
call {$fsdbDumpvars(0,"active_semantics_tb.chain_src","+all")}
call {$fsdbDumpvars(0,"active_semantics_tb.u_missing_probe.result","+all")}
call {$fsdbDumpvars(0,"active_semantics_tb.u_missing_probe.recorded_rhs","+all")}
call {$fsdbDumpMDA(0,"active_semantics_tb.u_dut")}
run
