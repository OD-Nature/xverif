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

CXXFLAGS = $(COMMON_CXXFLAGS) $(NPI_CXXFLAGS) -pthread -Isrc -Isrc/core -Isrc/engine -Isrc/design -Isrc/waveform -Ithird_party
LDFLAGS  = $(NPI_LDFLAGS) -pthread $(if $(NPI_LIB),-Xlinker -rpath -Xlinker $(NPI_LIB),)
DEPFLAGS = -MMD -MP
# Frontend does not need NPI (all NPI is in the engine subprocess).
FRONTEND_LDFLAGS = -pthread
BUILD    = build
LIBEXEC  = libexec
EXE      = xdebug
PYTHON  ?= python3
AXI_REFERENCE_ROOT ?= /home/yian/axi_test/test
SVT_VIP_INCDIR ?= /home/yian/axi_test/test/include/sverilog
SVT_VIP_SRCDIR ?= /home/yian/axi_test/test/src/sverilog/vcs

CORE_SRCS = src/core/common/tool_config.cpp \
            src/core/common/path_utils.cpp \
            src/core/npi/time_contract.cpp \
            src/core/transport/file_exchange.cpp \
            src/core/logging/action_log.cpp \
            src/core/session/session_types.cpp \
            src/core/process/process_runner.cpp \
            src/core/ai/common_blocks.cpp \
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
           src/session/session_catalog.cpp \
           src/backend/engine_adapter.cpp \
           src/runtime/work_dir.cpp

ENGINE_SRCS = src/engine/main.cpp \
              src/engine/engine_query.cpp \
              src/engine/server.cpp \
              src/engine/session/session_registry.cpp \
              src/engine/session/session_manager.cpp \
              src/engine/session/session_transport.cpp \
              src/engine/session/client.cpp \
              src/engine/service/engine_action_registry.cpp \
              src/engine/service/engine_action_handler.cpp \
              src/engine/service/trace_source_path_formatter.cpp \
              src/engine/service/actions/combined/register_combined_handlers.cpp \
              src/engine/service/actions/combined/trace_active_driver.cpp \
              src/engine/service/actions/combined/trace_active_driver_chain.cpp \
              src/engine/service/actions/design/expr_normalize.cpp \
              src/engine/service/actions/design/register_design_handlers.cpp \
              src/engine/service/actions/design/signal_canonicalize.cpp \
              src/engine/service/actions/design/signal_resolve.cpp \
              src/engine/service/actions/design/source_context.cpp \
              src/engine/service/actions/design/trace_driver.cpp \
              src/engine/service/actions/design/trace_load.cpp \
              src/engine/service/actions/protocol/apb_config_list.cpp \
              src/engine/service/actions/protocol/apb_config_load.cpp \
              src/engine/service/actions/protocol/apb_cursor.cpp \
              src/engine/service/actions/protocol/apb_query.cpp \
              src/engine/service/actions/protocol/axi_analysis.cpp \
              src/engine/service/actions/protocol/axi_config_list.cpp \
              src/engine/service/actions/protocol/axi_config_load.cpp \
              src/engine/service/actions/protocol/axi_cursor.cpp \
              src/engine/service/actions/protocol/axi_export.cpp \
              src/engine/service/actions/protocol/axi_query.cpp \
              src/engine/service/actions/protocol/register_protocol_handlers.cpp \
              src/engine/service/actions/stream/register_stream_handlers.cpp \
              src/engine/service/actions/stream/stream_config_list.cpp \
              src/engine/service/actions/stream/stream_config_load.cpp \
              src/engine/service/actions/stream/stream_export.cpp \
              src/engine/service/actions/stream/stream_query.cpp \
              src/engine/service/actions/stream/stream_show.cpp \
              src/engine/service/actions/stream/stream_validate.cpp \
              src/engine/service/actions/waveform/apb_transfer_window.cpp \
              src/engine/service/actions/waveform/axi_channel_stall.cpp \
              src/engine/service/actions/waveform/axi_latency_outlier.cpp \
              src/engine/service/actions/waveform/axi_outstanding_timeline.cpp \
              src/engine/service/actions/waveform/axi_request_response_pair.cpp \
              src/engine/service/actions/waveform/counter_statistics.cpp \
              src/engine/service/actions/waveform/cursor_delete.cpp \
              src/engine/service/actions/waveform/cursor_get.cpp \
              src/engine/service/actions/waveform/cursor_list.cpp \
              src/engine/service/actions/waveform/cursor_set.cpp \
              src/engine/service/actions/waveform/cursor_use.cpp \
              src/engine/service/actions/waveform/detect_anomaly.cpp \
              src/engine/service/actions/waveform/event_config_list.cpp \
              src/engine/service/actions/waveform/event_config_load.cpp \
              src/engine/service/actions/waveform/event_export.cpp \
              src/engine/service/actions/waveform/event_find.cpp \
              src/engine/service/actions/waveform/expr_eval_at.cpp \
              src/engine/service/actions/waveform/handshake_inspect.cpp \
              src/engine/service/actions/waveform/list_add.cpp \
              src/engine/service/actions/waveform/list_create.cpp \
              src/engine/service/actions/waveform/list_delete.cpp \
              src/engine/service/actions/waveform/list_diff.cpp \
              src/engine/service/actions/waveform/list_export.cpp \
              src/engine/service/actions/waveform/list_show.cpp \
              src/engine/service/actions/waveform/list_validate.cpp \
              src/engine/service/actions/waveform/list_value_at.cpp \
              src/engine/service/actions/waveform/rc_generate.cpp \
              src/engine/service/actions/waveform/register_waveform_handlers.cpp \
              src/engine/service/actions/waveform/sampled_pulse_inspect.cpp \
              src/engine/service/actions/waveform/scope_list.cpp \
              src/engine/service/actions/waveform/scope_roots.cpp \
              src/engine/service/actions/waveform/signal_changes.cpp \
              src/engine/service/actions/waveform/signal_stability.cpp \
              src/engine/service/actions/waveform/signal_statistics.cpp \
              src/engine/service/actions/waveform/value_at.cpp \
              src/engine/service/actions/waveform/value_batch_at.cpp \
              src/engine/service/actions/waveform/verify_conditions.cpp \
              src/engine/service/actions/waveform/window_verify.cpp \
              src/engine/service/design_postprocess.cpp \
              src/engine/service/trace_bfs_engine.cpp \
              src/api/response.cpp \
              src/api/text_response_builder.cpp \
              src/api/xout_renderer.cpp \
              src/runtime/work_dir.cpp \
              src/combined/active_trace_service.cpp \
              src/combined/active_trace_chain.cpp


DESIGN_SRCS = src/design/service/action_support.cpp \
              src/design/service/trace_actions.cpp \
              src/design/common/xdebug_design_paths.cpp \
              src/design/ast/ast_extractor.cpp \
              src/design/control_dep/control_dep.cpp \
              src/design/trace/trace_engine.cpp \
              src/design/signal/signal_finder.cpp

WAVEFORM_SRCS = src/waveform/service/action_support.cpp \
                src/waveform/service/value_support.cpp \
                src/waveform/service/config_support.cpp \
                src/waveform/service/rc_generator.cpp \
                src/waveform/value/logic_value.cpp \
                src/waveform/server/service/context.cpp \
                src/waveform/server/service/value_scope.cpp \
                src/waveform/server/service/signal_analysis.cpp \
                src/waveform/server/service/signal_inspect.cpp \
                src/waveform/server/service/query_actions.cpp \
                src/waveform/server/service/event_handlers.cpp \
                src/waveform/server/fsdb_value_reader.cpp \
                src/waveform/server/fsdb_scan_utils.cpp \
                src/waveform/export/waveform_exporter.cpp \
                src/waveform/list/list_manager.cpp \
                src/waveform/cursor/cursor_manager.cpp \
                src/waveform/common/xdebug_waveform_paths.cpp \
                src/waveform/common/time_spec.cpp \
                src/waveform/apb/apb_manager.cpp \
                src/waveform/apb/apb_analyzer.cpp \
                src/waveform/axi/axi_manager.cpp \
                src/waveform/axi/axi_analyzer.cpp \
                src/waveform/axi/axi_exporter.cpp \
                src/waveform/event/event_manager.cpp \
                src/waveform/event/event_expr.cpp \
                src/waveform/event/event_analyzer.cpp \
                src/waveform/stream/stream_config.cpp \
                src/waveform/stream/stream_manager.cpp \
                src/waveform/stream/stream_expr.cpp \
                src/waveform/stream/stream_analyzer.cpp \
                src/waveform/stream/stream_exporter.cpp

CORE_OBJS = $(CORE_SRCS:%.cpp=$(BUILD)/%.o)
API_SUPPORT_OBJS = $(API_SUPPORT_SRCS:%.cpp=$(BUILD)/%.o)
APP_OBJS = $(APP_SRCS:%.cpp=$(BUILD)/%.o)
ENGINE_OBJS = $(ENGINE_SRCS:%.cpp=$(BUILD)/%.o)
DESIGN_OBJS = $(DESIGN_SRCS:%.cpp=$(BUILD)/%.o)
WAVEFORM_OBJS = $(WAVEFORM_SRCS:%.cpp=$(BUILD)/%.o)
DEPS = $(sort $(CORE_OBJS:.o=.d) \
       $(API_SUPPORT_OBJS:.o=.d) \
       $(APP_OBJS:.o=.d) \
       $(ENGINE_OBJS:.o=.d) \
       $(DESIGN_OBJS:.o=.d) \
       $(WAVEFORM_OBJS:.o=.d))

.PHONY: all internal-engines unit-test log-test test-infra pytest-contract pytest-synthetic-existing pytest-counter-statistics pytest-axi-vip pytest-apb-vip pytest-active-semantics pytest-realdata pytest-session pytest-mcp test-fast test-contract test-synthetic test-vip test-active-trace test-session test-mcp-direct test-mcp-fake-lsf test-realdata-smoke test-regression test-nightly test-mcp-real-lsf mcp-test schema-test contract-test combined-test clean

all: $(EXE) internal-engines

internal-engines: $(LIBEXEC)/xdebug-engine

# Unified engine: engine + design helper + waveform helper objects.
UNIFIED_OBJS = $(ENGINE_OBJS) $(DESIGN_OBJS) $(WAVEFORM_OBJS)
$(LIBEXEC)/xdebug-engine: $(CORE_OBJS) $(UNIFIED_OBJS)
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -DXDEBUG_INTERNAL_ENGINE -o $@ $^ $(LDFLAGS)

$(EXE): $(CORE_OBJS) $(APP_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

$(BUILD)/%.o: %.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) $(DEPFLAGS) -DXDEBUG_INTERNAL_ENGINE -c -o $@ $<

unit-test: $(CORE_OBJS) $(API_SUPPORT_OBJS) $(BUILD)/src/api/response.o $(BUILD)/src/api/text_response_builder.o $(BUILD)/src/api/xout_renderer.o $(BUILD)/src/waveform/service/rc_generator.o $(BUILD)/src/waveform/value/logic_value.o $(BUILD)/src/session/session_catalog.o
	mkdir -p $(BUILD)/tests
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_core_types tests/unit/test_core_types.cpp $(CORE_OBJS) $(LDFLAGS)
	$(BUILD)/tests/test_core_types
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_unique_resource tests/unit/test_unique_resource.cpp
	$(BUILD)/tests/test_unique_resource
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_action_log tests/unit/test_action_log.cpp $(CORE_OBJS) $(LDFLAGS)
	$(BUILD)/tests/test_action_log
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_file_exchange tests/unit/test_file_exchange.cpp $(CORE_OBJS) $(LDFLAGS)
	$(BUILD)/tests/test_file_exchange
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_process_runner tests/unit/test_process_runner.cpp $(CORE_OBJS) $(LDFLAGS)
	$(BUILD)/tests/test_process_runner
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_session_catalog tests/unit/test_session_catalog.cpp $(BUILD)/src/session/session_catalog.o
	$(BUILD)/tests/test_session_catalog
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_action_registry tests/unit/test_action_registry.cpp $(CORE_OBJS) $(API_SUPPORT_OBJS) $(BUILD)/src/api/response.o $(LDFLAGS)
	$(BUILD)/tests/test_action_registry
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_request_contract tests/unit/test_request_contract.cpp $(CORE_OBJS) $(API_SUPPORT_OBJS) $(BUILD)/src/api/response.o $(LDFLAGS)
	$(BUILD)/tests/test_request_contract
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_text_response_builder tests/unit/test_text_response_builder.cpp $(BUILD)/src/api/text_response_builder.o $(BUILD)/src/api/xout_renderer.o
	$(BUILD)/tests/test_text_response_builder
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_common_blocks tests/unit/test_common_blocks.cpp $(CORE_OBJS) $(BUILD)/src/api/text_response_builder.o $(BUILD)/src/api/xout_renderer.o $(LDFLAGS)
	$(BUILD)/tests/test_common_blocks
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_logic_value tests/unit/test_logic_value.cpp $(BUILD)/src/waveform/value/logic_value.o
	$(BUILD)/tests/test_logic_value
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_rc_generator tests/unit/test_rc_generator.cpp $(BUILD)/src/waveform/service/rc_generator.o
	$(BUILD)/tests/test_rc_generator

log-test: $(CORE_OBJS) $(EXE) internal-engines
	mkdir -p $(BUILD)/tests
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_action_log tests/unit/test_action_log.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_action_log
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/session/test_stdio_loop_lifecycle.py
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/session/test_session_lifecycle.py -k "engine_crash_marker_is_written_by_signal_handler"
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/session/test_session_lifecycle.py -k "uds_direct_query_times_out_without_spawn_fallback or uds_connect_failure_is_logged or uds_invalid_json_response_is_logged"
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. \
		$(PYTHON) -m pytest -q $(CURDIR)/../xverif_mcp/tests/test_stdio_loop_session_lifecycle.py

test-infra:
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/unit/test_test_infra.py

pytest-contract: $(EXE)
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/contract

pytest-synthetic-existing: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/synthetic/test_existing_regressions.py

pytest-counter-statistics: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/synthetic/test_counter_statistics.py

pytest-axi-vip: all
	AXI_REFERENCE_ROOT=$(AXI_REFERENCE_ROOT) SVT_VIP_INCDIR=$(SVT_VIP_INCDIR) SVT_VIP_SRCDIR=$(SVT_VIP_SRCDIR) \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/synthetic/test_axi_vip_real.py

pytest-apb-vip: all
	SVT_VIP_INCDIR=$(SVT_VIP_INCDIR) SVT_VIP_SRCDIR=$(SVT_VIP_SRCDIR) \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/synthetic/test_apb_vip_real.py

pytest-active-semantics: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/combined/test_active_semantics.py

pytest-realdata: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/realdata

pytest-session: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/session

pytest-mcp: all
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/mcp

test-fast: test-infra schema-test unit-test contract-test pytest-contract

test-contract: test-fast

test-synthetic: pytest-synthetic-existing pytest-counter-statistics pytest-active-semantics

test-vip: pytest-axi-vip pytest-apb-vip

test-active-trace: pytest-active-semantics

test-session: pytest-session

test-mcp-direct: all
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/mcp -m "mcp_direct"

test-mcp-fake-lsf: all
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/mcp -m "mcp_fake_lsf"

test-realdata-smoke: pytest-realdata

test-regression: test-fast test-synthetic test-session test-mcp-direct test-mcp-fake-lsf test-realdata-smoke

test-nightly: test-regression test-vip
	@if [ "$$XDEBUG_ENABLE_REAL_LSF" = "1" ]; then \
		$(MAKE) test-mcp-real-lsf PYTHON=$(PYTHON); \
	else \
		echo "skip optional real LSF tests: set XDEBUG_ENABLE_REAL_LSF=1 and run make test-mcp-real-lsf"; \
	fi

test-mcp-real-lsf: all
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. XDEBUG_ENABLE_REAL_LSF=1 \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/mcp -m "mcp_real_lsf"

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

-include $(DEPS)
