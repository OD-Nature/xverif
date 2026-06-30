#include "service/engine_action_registry.h"

#include <memory>

namespace xdebug_design {

std::unique_ptr<EngineActionHandler> make_trace_driver_handler();
std::unique_ptr<EngineActionHandler> make_trace_load_handler();
std::unique_ptr<EngineActionHandler> make_signal_resolve_handler();
std::unique_ptr<EngineActionHandler> make_trace_query_handler();
std::unique_ptr<EngineActionHandler> make_trace_expand_handler();
std::unique_ptr<EngineActionHandler> make_trace_path_handler();
std::unique_ptr<EngineActionHandler> make_signal_canonicalize_handler();
std::unique_ptr<EngineActionHandler> make_source_context_handler();
std::unique_ptr<EngineActionHandler> make_expr_normalize_handler();
std::unique_ptr<EngineActionHandler> make_fsm_explain_handler();

void register_design_handlers(EngineActionRegistry& r) {
    r.add(make_trace_driver_handler());
    r.add(make_trace_load_handler());
    r.add(make_signal_resolve_handler());
    r.add(make_trace_query_handler());
    r.add(make_trace_expand_handler());
    r.add(make_trace_path_handler());
    r.add(make_signal_canonicalize_handler());
    r.add(make_source_context_handler());
    r.add(make_expr_normalize_handler());
    r.add(make_fsm_explain_handler());
}

} // namespace xdebug_design
