TOP ?= ..

include $(TOP)/mk/common_flags.mk

ifneq ($(MAKECMDGOALS),)
ifeq ($(filter-out schema-test,$(MAKECMDGOALS)),)
XDEBUG_SCHEMA_ONLY := 1
endif
endif

ifeq ($(XDEBUG_SCHEMA_ONLY),)
include $(TOP)/mk/npi.mk
endif

NPI_CXXFLAGS ?=
NPI_LDFLAGS ?=
NPI_LIB ?=

CXXFLAGS = $(COMMON_CXXFLAGS) $(NPI_CXXFLAGS) -pthread -Isrc -Isrc/core -Isrc/design -Isrc/waveform -Ithird_party
LDFLAGS  = $(NPI_LDFLAGS) -pthread $(if $(NPI_LIB),-Xlinker -rpath -Xlinker $(NPI_LIB),)
BUILD    = build
LIBEXEC  = libexec
EXE      = xdebug
PYTHON  ?= python3

CORE_SRCS = src/core/common/tool_config.cpp \
            src/core/common/path_utils.cpp \
            src/core/transport/file_exchange.cpp \
            src/core/logging/action_log.cpp \
            src/core/session/session_types.cpp \
            src/core/ai/ai_response.cpp

API_SUPPORT_SRCS = src/api/action_spec.cpp \
                   src/api/action_registry.cpp \
                   src/api/action_registry_init.cpp \
                   src/api/request_envelope.cpp \
                   src/api/request_validator.cpp \
                   src/api/resource_resolver.cpp \
                   src/api/response_builder.cpp

APP_SRCS = src/main.cpp \
           src/api/request_parser.cpp \
           src/api/response.cpp \
           src/api/help_text.cpp \
           src/api/text_response_builder.cpp \
           src/api/xout_renderer.cpp \
           src/api/action_catalog.cpp \
           src/api/dispatcher.cpp \
           src/api/stdio_loop.cpp \
           $(API_SUPPORT_SRCS) \
           src/session/session_store.cpp \
           src/backend/engine_adapter.cpp \
           src/runtime/work_dir.cpp \
           src/combined/active_trace_service.cpp

DESIGN_SRCS = src/design/main.cpp \
              src/design/session/session_registry.cpp \
              src/design/session/session_manager.cpp \
              src/design/session/session_transport.cpp \
              src/design/client/client.cpp \
              src/design/commands/cmd_ai.cpp \
              src/design/service/action_support.cpp \
              src/design/service/trace_actions.cpp \
              src/design/service/graph_actions.cpp \
              src/design/service/source_actions.cpp \
              src/design/service/semantic_actions.cpp \
              src/design/service/port_actions.cpp \
              src/design/service/router.cpp \
              src/design/server/server.cpp \
              src/design/common/xdebug_design_paths.cpp \
              src/design/ast/ast_extractor.cpp \
              src/design/port/port_analyzer.cpp \
              src/design/control_dep/control_dep.cpp \
              src/design/trace/trace_engine.cpp \
              src/design/signal/signal_finder.cpp

WAVEFORM_SRCS = src/waveform/main.cpp \
                src/waveform/session/session_registry.cpp \
                src/waveform/session/session_manager.cpp \
                src/waveform/session/session_transport.cpp \
                src/waveform/client/client.cpp \
                src/waveform/commands/cmd_ai.cpp \
                src/waveform/service/action_support.cpp \
                src/waveform/service/value_support.cpp \
                src/waveform/service/response_support.cpp \
                src/waveform/service/config_support.cpp \
                src/waveform/service/query_expression_support.cpp \
                src/waveform/service/rc_generator.cpp \
                src/waveform/service/session_actions.cpp \
                src/waveform/service/protocol_actions.cpp \
                src/waveform/service/router.cpp \
                src/waveform/server/server.cpp \
                src/waveform/server/service/context.cpp \
                src/waveform/server/service/value_scope.cpp \
                src/waveform/server/service/signal_analysis.cpp \
                src/waveform/server/service/signal_inspect.cpp \
                src/waveform/server/service/query_actions.cpp \
                src/waveform/server/service/event_handlers.cpp \
                src/waveform/server/service/request_router.cpp \
                src/waveform/server/fsdb_value_reader.cpp \
                src/waveform/server/fsdb_scan_utils.cpp \
                src/waveform/list/list_manager.cpp \
                src/waveform/cursor/cursor_manager.cpp \
                src/waveform/common/xdebug_waveform_paths.cpp \
                src/waveform/common/time_spec.cpp \
                src/waveform/common/time_parser.cpp \
                src/waveform/apb/apb_manager.cpp \
                src/waveform/apb/apb_analyzer.cpp \
                src/waveform/axi/axi_manager.cpp \
                src/waveform/axi/axi_analyzer.cpp \
                src/waveform/event/event_manager.cpp \
                src/waveform/event/event_expr.cpp \
                src/waveform/event/event_analyzer.cpp

CORE_OBJS = $(CORE_SRCS:%.cpp=$(BUILD)/%.o)
API_SUPPORT_OBJS = $(API_SUPPORT_SRCS:%.cpp=$(BUILD)/%.o)
APP_OBJS = $(APP_SRCS:%.cpp=$(BUILD)/%.o)
DESIGN_OBJS = $(DESIGN_SRCS:%.cpp=$(BUILD)/%.o)
WAVEFORM_OBJS = $(WAVEFORM_SRCS:%.cpp=$(BUILD)/%.o)

.PHONY: all internal-engines unit-test mcp-test schema-test contract-test combined-test clean

all: $(EXE) internal-engines

internal-engines: $(LIBEXEC)/xdebug-design-engine $(LIBEXEC)/xdebug-waveform-engine

$(EXE): $(CORE_OBJS) $(APP_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

$(LIBEXEC)/xdebug-design-engine: $(CORE_OBJS) $(DESIGN_OBJS)
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -DXDEBUG_INTERNAL_ENGINE -o $@ $^ $(LDFLAGS)

$(LIBEXEC)/xdebug-waveform-engine: $(CORE_OBJS) $(WAVEFORM_OBJS)
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -DXDEBUG_INTERNAL_ENGINE -o $@ $^ $(LDFLAGS)

$(BUILD)/%.o: %.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -DXDEBUG_INTERNAL_ENGINE -c -o $@ $<

unit-test: $(CORE_OBJS) $(API_SUPPORT_OBJS) $(BUILD)/src/api/response.o $(BUILD)/src/api/text_response_builder.o $(BUILD)/src/api/xout_renderer.o $(BUILD)/src/waveform/service/rc_generator.o
	mkdir -p $(BUILD)/tests
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_core_types tests/unit/test_core_types.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_core_types
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_action_log tests/unit/test_action_log.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_action_log
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_file_exchange tests/unit/test_file_exchange.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_file_exchange
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_action_registry tests/unit/test_action_registry.cpp $(CORE_OBJS) $(API_SUPPORT_OBJS) $(BUILD)/src/api/response.o
	$(BUILD)/tests/test_action_registry
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_text_response_builder tests/unit/test_text_response_builder.cpp $(BUILD)/src/api/text_response_builder.o $(BUILD)/src/api/xout_renderer.o
	$(BUILD)/tests/test_text_response_builder
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_rc_generator tests/unit/test_rc_generator.cpp $(BUILD)/src/waveform/service/rc_generator.o
	$(BUILD)/tests/test_rc_generator

schema-test:
	$(PYTHON) tools/validate_schema.py schemas/v1
	$(PYTHON) tools/validate_examples.py examples schemas/v1

mcp-test:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. $(PYTHON) $(CURDIR)/../xverif_mcp/tools/test_actions.py

mcp-test-schema:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. $(PYTHON) $(CURDIR)/../xverif_mcp/tools/test_actions.py --schema-only

mcp-test-lsf:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. XVERIF_MCP_BACKEND=lsf XVERIF_MCP_FAKE_LSF=1 $(PYTHON) $(CURDIR)/../xverif_mcp/tools/test_actions.py

mcp-session-test:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. $(PYTHON) -m pytest -q $(CURDIR)/../xverif_mcp/tests/test_stdio_loop_session_lifecycle.py $(CURDIR)/../xverif_mcp/tests/test_backend_wiring.py $(CURDIR)/../xverif_mcp/tests/test_session_errors.py -v

mcp-sdk-test:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. $(PYTHON) -m pytest -q $(CURDIR)/../xverif_mcp/tests/test_mcp_sdk_smoke.py -v

mcp-inspect:
	cd $(CURDIR)/.. && PYTHONPATH=xverif_mcp/src$(PYTHON) -m mcp dev xverif_mcp/src/xverif_mcp/server.py

mcp-run:
	cd $(CURDIR)/.. && PYTHONPATH=xverif_mcp/src$(PYTHON) -m mcp run xverif_mcp/src/xverif_mcp/server.py

contract-test: $(EXE) schema-test
	$(PYTHON) tools/audit_action_schema_coverage.py $(CURDIR)
	$(PYTHON) tools/check_action_contract.py specs/actions $(CURDIR)/$(EXE)

combined-test: $(EXE)
	$(PYTHON) tests/combined/run_active_driver_fixture.py

clean:
	rm -rf $(BUILD) $(LIBEXEC) $(EXE)
