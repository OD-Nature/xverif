TOP              ?= axi_vip_fixture_top
MODE             ?= regression
TC               ?= axi_multi_id_test
VCS              ?= vcs
VLOGAN           ?= vlogan
NPROC            ?= 4
AXI_REFERENCE_ROOT ?=
SVT_VIP_INCDIR   ?=
SVT_VIP_SRCDIR   ?=
VERDI_HOME       ?=

NUM_IDS          ?= 16
TRANS_PER_ID     ?= 200
OUTSTANDING_DEPTH ?= 4
MIN_DELAY        ?= 50
MAX_DELAY        ?= 100
SEED             ?= 7
VERBOSITY        ?= UVM_LOW

ROOT_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
OUTPUT_ROOT ?= $(ROOT_DIR)/out
OUT_DIR   := $(OUTPUT_ROOT)/$(MODE)
BUILD_DIR := $(OUT_DIR)/build
ANDB_DIR  := $(BUILD_DIR)/work
SIMV      := $(BUILD_DIR)/simv
RUN_DIR   := $(OUT_DIR)/test/$(TC)

VCS_SHARED := -full64 -sverilog -ntb_opts uvm-1.2 \
	+define+SVT_UVM_TECHNOLOGY \
	+define+UVM_PACKER_MAX_BYTES=1500000 \
	+define+UVM_DISABLE_AUTO_ITEM_RECORDING \
	+define+SVT_AXI_MAX_AXI3_GENERIC_DELAY=128 \
	+incdir+$(ROOT_DIR)/tb \
	+incdir+$(ROOT_DIR)/tb/env \
	+incdir+$(ROOT_DIR)/tests \
	+incdir+$(AXI_REFERENCE_ROOT)/tb \
	+incdir+$(AXI_REFERENCE_ROOT)/tb/env \
	+incdir+$(AXI_REFERENCE_ROOT)/tests \
	+incdir+$(SVT_VIP_INCDIR) \
	+incdir+$(SVT_VIP_SRCDIR) \
	-timescale=1ns/1ps -kdb -lca

SIM_OPTS := +UVM_TESTNAME=$(TC) \
	+UVM_VERBOSITY=$(VERBOSITY) \
	+uvm_set_verbosity=uvm_test_top.env.axi_system_env*,_ALL_,UVM_NONE,run \
	+num_ids=$(NUM_IDS) \
	+trans_per_id=$(TRANS_PER_ID) \
	+outstanding_depth=$(OUTSTANDING_DEPTH) \
	+min_delay=$(MIN_DELAY) \
	+max_delay=$(MAX_DELAY) \
	+ntb_random_seed=$(SEED) \
	+fsdb+force +fsdb+autoflush +fsdbfile+waves.fsdb \
	-l sim.log

.PHONY: check-env vlog_com vlog_rtl vlog_tb elab cmp ncrun mrun run clean

check-env:
	@test -n "$(AXI_REFERENCE_ROOT)" || { echo "AXI_REFERENCE_ROOT is required"; exit 2; }
	@test -f "$(AXI_REFERENCE_ROOT)/tests/test_pkg.sv" || { echo "invalid AXI_REFERENCE_ROOT=$(AXI_REFERENCE_ROOT)"; exit 2; }
	@test -f "$(SVT_VIP_INCDIR)/svt_axi_if.svi" || { echo "SVT_VIP_INCDIR must contain svt_axi_if.svi"; exit 2; }
	@test -f "$(SVT_VIP_INCDIR)/svt_axi.uvm.pkg" || { echo "SVT_VIP_INCDIR must contain svt_axi.uvm.pkg"; exit 2; }
	@test -d "$(SVT_VIP_SRCDIR)" || { echo "SVT_VIP_SRCDIR is required"; exit 2; }

vlog_com: check-env
	@mkdir -p $(ANDB_DIR)
	cd $(ANDB_DIR) && $(VLOGAN) $(VCS_SHARED) -l $(BUILD_DIR)/vlog_com.log

vlog_rtl: check-env
	@mkdir -p $(ANDB_DIR)
	cd $(ANDB_DIR) && $(VLOGAN) $(VCS_SHARED) \
		$(AXI_REFERENCE_ROOT)/tb/dut_wrapper.sv \
		-l $(BUILD_DIR)/vlog_rtl.log

vlog_tb: check-env
	@mkdir -p $(ANDB_DIR)
	cd $(ANDB_DIR) && $(VLOGAN) $(VCS_SHARED) \
		$(SVT_VIP_INCDIR)/svt_axi_if.svi \
		$(SVT_VIP_INCDIR)/svt_axi.uvm.pkg \
		$(ROOT_DIR)/tests/test_pkg.sv \
		$(ROOT_DIR)/tb/axi_vip_fixture_top.sv \
		-l $(BUILD_DIR)/vlog_tb.log

elab:
	cd $(ANDB_DIR) && $(VCS) -full64 -sverilog -ntb_opts uvm-1.2 \
		-debug_access+all -kdb -lca -timescale=1ns/1ps \
		-j$(NPROC) -top $(TOP) -o $(SIMV) -l $(BUILD_DIR)/elab.log

cmp: vlog_com vlog_rtl vlog_tb elab

ncrun:
	@test -x $(SIMV) || { echo "missing $(SIMV); run make cmp first"; exit 2; }
	@mkdir -p $(RUN_DIR)
	cd $(RUN_DIR) && $(SIMV) $(SIM_OPTS)
	@test -s $(RUN_DIR)/waves.fsdb
	@test -d $(BUILD_DIR)/simv.daidir
	@grep -q "UVM_ERROR :    0" $(RUN_DIR)/sim.log
	@grep -q "UVM_FATAL :    0" $(RUN_DIR)/sim.log
	@grep -q "TEST PASSED - All data comparisons OK" $(RUN_DIR)/sim.log

mrun: vlog_tb elab ncrun

run: cmp ncrun

clean:
	rm -rf $(OUT_DIR)
