#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "service/design_postprocess.h"
#include "service/trace_bfs_engine.h"
#include "design_action_helpers.h"

#include "core/ai/common_blocks.h"

#include "design/trace/trace_engine.h"
#include "design/signal/signal_finder.h"
#include "design/service/action_support.h"
#include "combined/active_trace_common.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_L1.h"

#include <fstream>
#include <map>
#include <memory>
#include <set>

namespace xdebug_design {
namespace {
class SignalCanonicalizeHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "signal.canonicalize"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string query = args.value("signal", "");
        if (query.empty()) return make_handler_error(
            "MISSING_FIELD",
            "args.signal is required",
            {{"invalid_arg", "args.signal"},
             {"expected", "signal path or signal-like query"},
             {"correct_example", {{"api_version", "xdebug.v1"},
                                  {"action", "signal.canonicalize"},
                                  {"args", {{"signal", "top.u.valid"}}}}}});

        SignalResolveResult result;
        Json failure;
        if (!resolve_design_signal(action_name(), query, result, failure)) return failure;
        const SignalMatch& match = result.matches.front();
        const std::string resolved_signal = match.signal;
        xdebug::PortConnectionInfo port = xdebug::resolve_input_port_connection(resolved_signal);
        const std::string canonical = !port.target_signal.empty() ? port.target_signal : resolved_signal;
        const size_t dot = canonical.rfind('.');
        const std::string scope = dot == std::string::npos ? std::string() : canonical.substr(0, dot);
        const std::string leaf = dot == std::string::npos ? canonical : canonical.substr(dot + 1);
        Json aliases = Json::array();
        if (canonical != resolved_signal) aliases.push_back(resolved_signal);
        if (query != resolved_signal && query != canonical) aliases.push_back(query);
        Json port_mappings = Json::array();
        if (port.found_port) {
            port_mappings.push_back({{"instance", port.instance_path},
                                     {"port", port.port_name},
                                     {"direction", port.is_input_like ? "input_or_inout" : "output"},
                                     {"port_signal", resolved_signal},
                                     {"connected_signal", port.target_signal.empty()
                                         ? Json(nullptr) : Json(port.target_signal)},
                                     {"evidence", "npi_static_port_connection"}});
        }
        return Json{{"summary", {{"status", "found"}, {"query", query},
                                  {"ambiguous", result.matches.size() > 1},
                                  {"canonicalization_scope", "static_design_connectivity"}}},
                    {"canonical", canonical}, {"rtl_path", canonical},
                    {"leaf", leaf}, {"scope", scope}, {"base_signal", canonical},
                    {"select", nullptr}, {"aliases", aliases},
                    {"fsdb_candidates", Json::array()}, {"port_mappings", port_mappings}};
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_signal_canonicalize_handler() {
    return std::unique_ptr<EngineActionHandler>(new SignalCanonicalizeHandler);
}

}  // namespace xdebug_design
