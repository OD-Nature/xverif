TOP      ?= rc_arrays_tb
RUN_DIR  ?= out
VCS      ?= vcs
VCS_OPTS ?= -full64 -sverilog -timescale=1ns/1ps -debug_access+all -kdb -lca
ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: all fixture
all: fixture

fixture:
	mkdir -p $(RUN_DIR)
	cd $(RUN_DIR) && $(VCS) $(VCS_OPTS) $(ROOT_DIR)/rc_arrays_tb.sv -top $(TOP) -o simv -l compile.log
	cd $(RUN_DIR) && ./simv -l run.log
