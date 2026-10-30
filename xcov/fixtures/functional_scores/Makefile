RUN_DIR ?= out
SOURCE := $(abspath functional_scores.sv)
VDB := $(abspath $(RUN_DIR)/functional_scores.vdb)
SIMV := $(abspath $(RUN_DIR)/simv)

.PHONY: fixture
fixture:
	mkdir -p "$(RUN_DIR)"
	cd "$(RUN_DIR)" && \
		vcs -full64 -sverilog -kdb -debug_access+all -cm line+cond+branch+tgl+fsm+assert \
			-cm_dir "$(VDB)" -o "$(SIMV)" "$(SOURCE)" -top functional_scores
	cd "$(RUN_DIR)" && \
		"$(SIMV)" -cm line+cond+branch+tgl+fsm+assert \
			-cm_dir "$(VDB)" -cm_name functional_scores
