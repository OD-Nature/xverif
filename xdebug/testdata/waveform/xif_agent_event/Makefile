VCS        ?= vcs
VERDI_HOME ?= ~/Synopsys/verdi/V-2023.12-SP2
XIF_AGENT  ?= ~/xif_agent
XDEBUG     ?= ../../../../tools/xdebug

OUT        := out
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
	+incdir+tb \
	+define+XIF_EVENT_FSDB_DIR=\"$(OUT)/waves\" \
	-P $(NOVAS_TAB) $(NOVAS_PLI) \
	-f filelist.f \
	-o $(SIMV)

.PHONY: all sim run check clean

all: sim

sim:
	@test -f "$(NOVAS_TAB)"
	@test -f "$(NOVAS_PLI)"
	@mkdir -p $(OUT)/build $(OUT)/logs $(OUT)/waves
	$(VCS) $(VCS_FLAGS) -l $(OUT)/build/compile.log

run: sim
	@mkdir -p $(OUT)/logs $(OUT)/waves
	./$(SIMV) +UVM_TESTNAME=$(TEST) -l $(OUT)/logs/$(TEST).log

check: run
	python3 scripts/check_event_waves.py --xdebug $(XDEBUG) --fsdb $(OUT)/waves/$(TEST).fsdb

clean:
	rm -rf $(OUT) csrc simv simv.daidir ucli.key novas* verdiLog .vcs_lib_lock
