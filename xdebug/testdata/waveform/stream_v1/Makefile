TOP      ?= stream_v1_top
RUN_DIR  ?= out
VCS      ?= vcs
VCS_OPTS ?= -full64 -sverilog -timescale=1ns/1ps -debug_access+all -kdb -lca
ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: all compile run clean

all: run

$(RUN_DIR):
	mkdir -p $(RUN_DIR)

compile: $(RUN_DIR)
	cd $(RUN_DIR) && $(VCS) $(VCS_OPTS) $(ROOT_DIR)/tb/stream_v1_top.sv -top $(TOP) -l compile.log

run: compile
	cd $(RUN_DIR) && ./simv -l run.log

clean:
	rm -rf $(RUN_DIR) csrc simv.daidir ucli.key vc_hdrs.h verdiLog
