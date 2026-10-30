RUN_DIR ?= out
SOURCE := $(abspath design.sv)
VDB := $(abspath $(RUN_DIR)/no_functional.vdb)
SIMV := $(abspath $(RUN_DIR)/simv)
COVERAGE := line+cond+branch+tgl+fsm+assert

.PHONY: fixture
fixture:
	mkdir -p "$(RUN_DIR)"
	cd "$(RUN_DIR)" && \
		vcs -full64 -sverilog -kdb -debug_access+all \
			-cm $(COVERAGE) -cm_dir "$(VDB)" \
			"$(SOURCE)" -top code_only -o "$(SIMV)"
	cd "$(RUN_DIR)" && \
		"$(SIMV)" -cm $(COVERAGE) -cm_dir "$(VDB)" -cm_name code_only
