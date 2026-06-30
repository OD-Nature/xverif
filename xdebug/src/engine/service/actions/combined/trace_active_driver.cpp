#include "service/engine_action_handler.h"
#include "service/engine_globals.h"
#include "service/trace_source_path_formatter.h"

#include "combined/active_trace_service.h"
#include "combined/active_trace_chain.h"
#include "core/ai/common_blocks.h"

#include <memory>
#include <string>

namespace xdebug_design {
namespace {

class ActiveDriverHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.active_driver"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", std::string());
        std::string requested_time = args.value("requested_time", std::string());
        Json trace_request = request;
        if (!trace_request.contains("args") || !trace_request["args"].is_object()) {
            trace_request["args"] = Json::object();
        }
        trace_request["args"]["include_trace"] = true;
        Json raw = xdebug::build_active_driver_payload(trace_request, g_daidir_path, g_fsdb_path, g_fsdb_file);
        if (raw.contains("error")) return raw;
        Json out = simplify_active_driver_payload(raw,
                                                  signal,
                                                  requested_time,
                                                  trace_result_limit_from_request(request));
        xdebug::append_common_blocks_to_payload(out);
        return out;
    }

    std::string render_xout(const Json& response) const override {
        return append_common_blocks_xout(render_source_path_xout(action_name(), response), response);
    }
};

} // namespace

std::unique_ptr<EngineActionHandler> make_trace_active_driver_handler() {
    return std::unique_ptr<EngineActionHandler>(new ActiveDriverHandler);
}

} // namespace xdebug_design
