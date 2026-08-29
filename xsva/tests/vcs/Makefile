# xsva VCS 语义验证 Makefile
# 编译选项参考 <xring-repo>/dv/cfg/Makefile
# Usage:
#   make cmp   CASE=simple_impl   # compile
#   make run   CASE=simple_impl   # run
#   make all                     # all cases compile + run

VCS      ?= vcs
VLOGAN   ?= vlogan
CASE     ?= simple_impl

ROOT_DIR   = $(CURDIR)
CASE_DIR   = $(ROOT_DIR)/cases/$(CASE)
TB_DIR     = $(ROOT_DIR)/tb
OUTPUT_ROOT ?= $(ROOT_DIR)/out
OUT_DIR    = $(OUTPUT_ROOT)/$(CASE)
BUILD_DIR  = $(OUT_DIR)/build
ANDB_DIR   = $(BUILD_DIR)/work
SIMV       = $(BUILD_DIR)/simv

VCS_SHARED = -full64 -sverilog \
             -timescale=1ns/1ps \
             -kdb -lca \
             +incdir+$(ROOT_DIR) \
             +define+XSVA_VCS_TEST

SIM_OPTS   = +fsdb+force +fsdb+autoflush +fsdbfile+waves.fsdb \
             -ucli -do $(ROOT_DIR)/wave.tcl \
             -l sim.log

.PHONY: cmp run clean

cmp:
	@echo "[xsva VCS] compiling $(CASE)..."
	@mkdir -p $(ANDB_DIR)
	cd $(ANDB_DIR) && $(VLOGAN) $(VCS_SHARED) \
		$(CASE_DIR)/dut.sv \
		$(TB_DIR)/xsva_vcs_tb.sv \
		-l $(BUILD_DIR)/vlogan.log
	cd $(ANDB_DIR) && $(VCS) -full64 -sverilog \
		-debug_access+all -kdb -lca \
		-timescale=1ns/1ps \
		-top xsva_vcs_tb \
		-o $(SIMV) -l $(BUILD_DIR)/elab.log

run:
	@if [ ! -f $(SIMV) ]; then \
		echo "Run 'make cmp CASE=$(CASE)' first."; exit 1; \
	fi
	@echo "[xsva VCS] running $(CASE)..."
	@mkdir -p $(OUT_DIR)
	cd $(OUT_DIR) && $(SIMV) $(SIM_OPTS)
	@echo ""
	@grep -i "assertion\|failure\|Summary" $(OUT_DIR)/sim.log 2>/dev/null || true

clean:
	rm -rf $(OUT_DIR)
