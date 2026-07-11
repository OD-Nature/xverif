TOP ?= uart_16550
VCS ?= vcs
VCS_OPTS ?= -full64 -sverilog -kdb -debug_access+all

.PHONY: fixture clean

fixture: simv.daidir

simv.daidir: dut.f uart_16550.sv uart_register_file.sv uart_rx.sv uart_rx_fifo.sv uart_tx.sv uart_tx_fifo.sv
	$(VCS) $(VCS_OPTS) -f dut.f -top $(TOP) -o simv -l compile.log
	test -d simv.daidir

clean:
	rm -rf simv simv.daidir csrc compile.log ucli.key vc_hdrs.h verdiLog
