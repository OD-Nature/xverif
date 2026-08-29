TOP              ?= apb_vip_fixture_top
MODE             ?= regression
TC               ?= apb_vip_test
VCS              ?= vcs
VLOGAN           ?= vlogan
NPROC            ?= 4
SVT_VIP_INCDIR    ?= $(SVT_AMBA_VIP_HOME)/sverilog/include
SVT_VIP_SRCDIR    ?= $(SVT_AMBA_VIP_HOME)/sverilog/src/vcs
SVT_COMMON_INCDIR ?= $(SVT_COMMON_HOME)/sverilog/include
SVT_COMMON_SRCDIR ?= $(SVT_COMMON_HOME)/sverilog/src/vcs

SEED             ?= 11
VERBOSITY        ?= UVM_MEDIUM

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
	+define+SYNOPSYS_SV \
	+define+DESIGNWARE_INCDIR=$(DESIGNWARE_HOME) \
	+define+SVT_LOADER_UTIL_ENABLE_DWHOME_INCDIRS \
	+define+SVT_APB_MAX_ADDR_WIDTH=32 \
	+define+SVT_APB_MAX_DATA_WIDTH=32 \
	+incdir+$(ROOT_DIR)/env \
	+incdir+$(ROOT_DIR)/seq \
	+incdir+$(ROOT_DIR)/tests \
	+incdir+$(ROOT_DIR)/tb \
	+incdir+$(SVT_VIP_INCDIR) \
	+incdir+$(SVT_VIP_SRCDIR) \
	+incdir+$(SVT_COMMON_INCDIR) \
	+incdir+$(SVT_COMMON_SRCDIR) \
	-timescale=1ns/1ps -kdb -lca

SIM_OPTS := +UVM_TESTNAME=$(TC) \
	+UVM_VERBOSITY=$(VERBOSITY) \
	+ntb_random_seed=$(SEED) \
	+fsdb+force +fsdb+autoflush +fsdbfile+waves.fsdb \
	-l sim.log

.PHONY: check-env vlog_com vlog_rtl vlog_tb elab cmp ncrun run clean

check-env:
	@test -n "$(DESIGNWARE_HOME)" || { echo "DESIGNWARE_HOME is required"; exit 2; }
	@test -n "$(SVT_AMBA_VIP_HOME)" || { echo "SVT_AMBA_VIP_HOME is required"; exit 2; }
	@test -n "$(SVT_COMMON_HOME)" || { echo "SVT_COMMON_HOME is required"; exit 2; }
	@test -d "$(DESIGNWARE_HOME)/vip/svt" || { echo "DESIGNWARE_HOME must contain vip/svt"; exit 2; }
	@test -f "$(SVT_VIP_INCDIR)/svt_apb_if.svi" || { echo "SVT_VIP_INCDIR must contain svt_apb_if.svi"; exit 2; }
	@test -f "$(SVT_VIP_INCDIR)/svt_apb.uvm.pkg" || { echo "SVT_VIP_INCDIR must contain svt_apb.uvm.pkg"; exit 2; }
	@test -d "$(SVT_VIP_SRCDIR)" || { echo "SVT_VIP_SRCDIR is required"; exit 2; }
	@test -f "$(SVT_COMMON_INCDIR)/svt_defines.svi" || { echo "SVT_COMMON_INCDIR must contain svt_defines.svi"; exit 2; }
	@test -d "$(SVT_COMMON_SRCDIR)" || { echo "SVT_COMMON_SRCDIR is required"; exit 2; }

vlog_com: check-env
	@mkdir -p $(ANDB_DIR)
	cd $(ANDB_DIR) && $(VLOGAN) $(VCS_SHARED) -l $(BUILD_DIR)/vlog_com.log

vlog_rtl: check-env
	@mkdir -p $(ANDB_DIR)
	cd $(ANDB_DIR) && $(VLOGAN) $(VCS_SHARED) \
		$(ROOT_DIR)/tb/apb_slave_dut.sv \
		-l $(BUILD_DIR)/vlog_rtl.log

vlog_tb: check-env
	@mkdir -p $(ANDB_DIR)
	cd $(ANDB_DIR) && $(VLOGAN) $(VCS_SHARED) \
		$(SVT_VIP_INCDIR)/svt_apb.uvm.pkg \
		$(SVT_VIP_INCDIR)/svt_apb_if.svi \
		$(ROOT_DIR)/apb_vip_pkg.sv \
		$(ROOT_DIR)/tb/apb_vip_fixture_top.sv \
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
	@grep -q "APB VIP fixture completed: writes=5 reads=5 errors=1" $(RUN_DIR)/sim.log

run: cmp ncrun

clean:
	rm -rf $(OUT_DIR)
