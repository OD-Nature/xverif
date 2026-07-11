VCS ?= vcs
RUN_DIR ?= out
CM ?= line+tgl+branch

.PHONY: fixture clean

fixture: $(RUN_DIR)/simv.vdb/snps/coverage/db

$(RUN_DIR)/simv.vdb/snps/coverage/db: dut.sv tb.sv
	mkdir -p $(RUN_DIR)
	cd $(RUN_DIR) && $(VCS) -full64 -sverilog -timescale=1ns/1ps \
		-cm $(CM) ../dut.sv ../tb.sv -top xcov_basic_tb -o simv -l compile.log
	cd $(RUN_DIR) && ./simv +TEST_MODE=0 -cm $(CM) -cm_name basic_a -l basic_a.log
	cd $(RUN_DIR) && ./simv +TEST_MODE=1 -cm $(CM) -cm_name basic_b -l basic_b.log
	test -n "$$(find $(RUN_DIR)/simv.vdb/snps/coverage/db -type f -print -quit)"

clean:
	rm -rf $(RUN_DIR)
