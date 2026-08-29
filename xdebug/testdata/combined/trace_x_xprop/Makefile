TOP      ?= trace_x_xprop_tb
RUN_DIR  ?= out
VCS      ?= vcs
VCS_OPTS ?= -full64 -sverilog -timescale=1ns/1ps -debug_access+all -kdb -lca -xprop=tmerge
ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: all fixture clean

all: fixture

$(RUN_DIR):
	mkdir -p $(RUN_DIR)

fixture: $(RUN_DIR)
	cd $(RUN_DIR) && $(VCS) $(VCS_OPTS) $(ROOT_DIR)/trace_x_xprop_tb.sv -top $(TOP) -o simv -l compile.log
	cd $(RUN_DIR) && ./simv +fsdb+force +fsdb+autoflush +fsdbfile+waves.fsdb -ucli -ucli2Proc -do $(ROOT_DIR)/wave.tcl -l run.log

clean:
	rm -rf $(RUN_DIR) csrc simv.daidir ucli.key verdiLog
