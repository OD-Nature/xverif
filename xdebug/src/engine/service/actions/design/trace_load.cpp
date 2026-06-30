#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "service/design_postprocess.h"
#include "service/trace_bfs_engine.h"
#include "service/trace_source_path_formatter.h"

#include "core/ai/common_blocks.h"

#include "design/trace/trace_engine.h"
#include "design/signal/signal_finder.h"
#include "design/service/action_support.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_L1.h"

#include <fstream>
#include <map>
#include <memory>
#include <set>

namespace xdebug_design {
namespace {

static TraceOptions parse_trace_opts(const Json& args) {
    TraceOptions opts;
    opts.limit = args.value("limit", 0);
    opts.role = args.value("role", std::string());
    opts.no_statement_only = args.value("no_statement_only", false);
    if (args.contains("include_statement_only") && args["include_statement_only"].is_boolean())
        opts.no_statement_only = !args["include_statement_only"].get<bool>();
    return opts;
}

class TraceLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.load"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }

    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", std::string());
        if (signal.empty()) return err("MISSING_FIELD", "args.signal is required");
        TraceEngine engine;
        TraceResult result = engine.trace(signal, TraceMode::Load, parse_trace_opts(args));
        Json raw = Json::parse(engine.render_ai_json(result));
        Json out = simplify_trace_driver_load_payload(raw, action_name(), signal, "load");
        xdebug::append_common_blocks_to_payload(out);
        return out;
    }

    std::string render_xout(const Json& response) const override {
        return append_common_blocks_xout(render_source_path_xout(action_name(), response), response);
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_trace_load_handler() {
    return std::unique_ptr<EngineActionHandler>(new TraceLoadHandler);
}

}  // namespace xdebug_design
