VCS        ?= vcs
XIF_AGENT  ?= $(abspath $(CURDIR)/../../../../third_party/xif_agent)
SOURCE_DIR := $(abspath .)
WAVE_TCL   := $(SOURCE_DIR)/wave.tcl

OUT        ?= out
SIMV       := $(OUT)/simv
TEST       ?= xif_event_multi_if_test
VCS_FLAGS := \
	-full64 \
	-sverilog \
	-ntb_opts uvm-1.2 \
	-timescale=1ns/1ps \
	-debug_access+all \
	-kdb \
	-lca \
	+incdir+$(XIF_AGENT)/src \
	+incdir+$(SOURCE_DIR)/tb \
	$(XIF_AGENT)/src/xif_pkg.sv \
	$(XIF_AGENT)/src/xif_if.sv \
	$(XIF_AGENT)/src/xif_agent_pkg.sv \
	$(SOURCE_DIR)/tb/xif_event_pkg.sv \
	$(SOURCE_DIR)/tb/xif_event_top.sv

.PHONY: all sim run clean

all: sim

sim:
	@mkdir -p $(OUT)/build $(OUT)/logs $(OUT)/waves
	cd $(OUT) && $(VCS) $(VCS_FLAGS) -o simv -l build/compile.log

run: sim
	@mkdir -p $(OUT)/logs $(OUT)/waves
	cd $(OUT) && ./simv +UVM_TESTNAME=$(TEST) \
		+fsdb+force +fsdb+autoflush +fsdbfile+waves/$(TEST).fsdb \
		-ucli -ucli2Proc -do $(WAVE_TCL) -l logs/$(TEST).log

clean:
	rm -rf $(OUT) csrc simv simv.daidir ucli.key novas* verdiLog .vcs_lib_lock
