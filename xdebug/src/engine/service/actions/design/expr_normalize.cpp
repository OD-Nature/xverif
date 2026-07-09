#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "service/design_postprocess.h"
#include "service/trace_bfs_engine.h"

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
    opts.limit = args.value("line_limit", 0);
    opts.role = args.value("role", std::string());
    opts.no_statement_only = args.value("no_statement_only", false);
    if (args.contains("include_statement_only") && args["include_statement_only"].is_boolean())
        opts.no_statement_only = !args["include_statement_only"].get<bool>();
    return opts;
}
static nlohmann::json trace_one_signal(const std::string& signal,
                                        TraceMode mode,
                                        const TraceOptions& opts) {
    TraceEngine engine;
    TraceResult r = engine.trace(signal, mode, opts);
    return nlohmann::json::parse(engine.render_ai_json(r));
}

class ExprNormalizeHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "expr.normalize"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");

        Json out;
        if (!signal.empty()) {
            TraceOptions opts = parse_trace_opts(args);
            nlohmann::json trace = trace_one_signal(signal, TraceMode::Driver, opts);
            nlohmann::json assignment = trace.value("assignment", nlohmann::json::object());
            out["summary"] = {{"signal",signal},{"source","npi_trace_assignment"},
                {"confidence",trace.value("confidence","unknown")}};
            out["expr"] = Json::parse(
                assignment.value("rhs", nlohmann::json::object()).dump());
            out["assignment"] = Json::parse(assignment.dump());
            out["rhs_signals"] = Json::parse(
                assignment.value("rhs_signals", nlohmann::json::array()).dump());
            out["confidence"] = trace.value("confidence", "unknown");
            return out;
        }
        std::string expr = args.value("expr", "");
        if (expr.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.expr or args.signal"}});
        out["summary"] = {{"expr",expr},{"source","string_fallback"},{"confidence","low"}};
        out["expr"] = Json::parse(parse_expr_ast(expr).dump());
        out["confidence"] = "low";
        out["confidence_reason"] = "parsed from raw string without NPI handle";
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_expr_normalize_handler() {
    return std::unique_ptr<EngineActionHandler>(new ExprNormalizeHandler);
}

}  // namespace xdebug_design
