#include "action_support.h"

namespace xdebug_design {

json run_port_like_action(const json& request, const std::string& action) {
    json response = base_response(request, action);
    std::string session_id;
    SessionInfo session;
    if (!ensure_target_session(request, response, session_id, session)) return response;
    json args = request.value("args", json::object());
    std::string path = args.value("path", args.value("instance", args.value("signal", args.value("interface", ""))));
    if (path.empty()) {
        return error_response(request, action, "MISSING_FIELD", "args.path, args.instance, args.signal, or args.interface is required");
    }
    int limit = request.value("limits", json::object()).value("max_results", args.value("limit", 0));
    json rpc_args = {{"path", path}};
    if (limit > 0) rpc_args["limit"] = limit;
    json payload;
    std::string status, message;
    json engine_error;
    if (!send_json_command(session_id, action, rpc_args, payload, status, message, engine_error)) {
        if (!engine_error.is_null()) {
            response["ok"] = false;
            response["error"] = engine_error;
            return response;
        }
        return error_response(request, action, "SESSION_UNHEALTHY", message.empty() ? status : message);
    }
    response["ok"] = payload.value("ok", true);
    response["summary"] = {{"query", payload.value("query", path)}, {"port_count", payload.value("port_count", 0)},
        {"modport_port_count", payload.value("modport_port_count", 0)}, {"truncated", payload.value("truncated", false)}};
    response["data"] = payload;
    response["meta"]["truncated"] = payload.value("truncated", false);
    if (!response["ok"].get<bool>()) {
        json err = payload.value("error", json::object());
        response["error"] = {{"code", err.value("code", "TRACE_NO_RESULT")},
            {"message", err.value("message", "port/interface query failed")}, {"recoverable", true},
            {"candidates", json::array()}, {"suggested_actions", json::array()}};
    }
    return response;
}

} // namespace xdebug_design
