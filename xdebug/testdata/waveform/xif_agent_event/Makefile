VCS        ?= vcs
VERDI_HOME ?= ~/Synopsys/verdi/V-2023.12-SP2
XIF_AGENT  ?= $(HOME)/xif_agent
SOURCE_DIR := $(abspath .)

OUT        ?= out
SIMV       := $(OUT)/simv
TEST       ?= xif_event_multi_if_test
NOVAS_TAB  := $(VERDI_HOME)/share/PLI/VCS/linux64/novas.tab
NOVAS_PLI  := $(VERDI_HOME)/share/PLI/VCS/linux64/pli.a

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
	+define+XIF_EVENT_FSDB_DIR=\"waves\" \
	-P $(NOVAS_TAB) $(NOVAS_PLI) \
	$(XIF_AGENT)/src/xif_pkg.sv \
	$(XIF_AGENT)/src/xif_if.sv \
	$(XIF_AGENT)/src/xif_agent_pkg.sv \
	$(SOURCE_DIR)/tb/xif_event_pkg.sv \
	$(SOURCE_DIR)/tb/xif_event_top.sv

.PHONY: all sim run clean

all: sim

sim:
	@test -f "$(NOVAS_TAB)"
	@test -f "$(NOVAS_PLI)"
	@mkdir -p $(OUT)/build $(OUT)/logs $(OUT)/waves
	cd $(OUT) && $(VCS) $(VCS_FLAGS) -o simv -l build/compile.log

run: sim
	@mkdir -p $(OUT)/logs $(OUT)/waves
	cd $(OUT) && ./simv +UVM_TESTNAME=$(TEST) -l logs/$(TEST).log

clean:
	rm -rf $(OUT) csrc simv simv.daidir ucli.key novas* verdiLog .vcs_lib_lock
