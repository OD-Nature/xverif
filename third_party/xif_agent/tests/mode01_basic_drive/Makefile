VCS              ?= vcs
SIMV             := simv
TEST             ?= mode01_basic_drive_test

SV_SRCS          := $(wildcard ../../src/*.sv *.sv)

VCS_FLAGS := \
	-full64 \
	-sverilog \
	-ntb_opts uvm-1.2 \
	-timescale=1ns/1ps \
	-debug_access+all \
	-kdb \
	-lca \
	+vcs+lic+wait \
	+incdir+../../src \
	+incdir+. \
	-f filelist.f \
	-o $(SIMV)

RUN_FLAGS := +UVM_TESTNAME=$(TEST)

.PHONY: all sim run clean

all: sim

sim: $(SIMV)

$(SIMV): filelist.f $(SV_SRCS)
	@mkdir -p logs waves
	$(VCS) $(VCS_FLAGS) -l logs/compile.log

run: $(SIMV)
	@mkdir -p logs waves
	./$(SIMV) $(RUN_FLAGS) -l logs/$(TEST).log

clean:
	rm -rf simv simv.daidir csrc ucli.key logs waves novas* verdiLog .vcs_lib_lock
