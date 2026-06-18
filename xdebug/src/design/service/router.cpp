#include "action_support.h"
#include "logging/action_log.h"

#include <chrono>

namespace xdebug_design {

namespace {

json run_batch(const json& request) {
    json response = base_response(request, "batch");
    json args = request.value("args", json::object());
    json requests = args.value("requests", json::array());
    std::string mode = args.value("mode", "continue_on_error");
    json results = json::array();
    bool all_ok = true;
    for (auto child : requests) {
        if (!child.contains("api_version")) child["api_version"] = API_VERSION;
        json child_resp = handle_request(child);
        if (!child_resp.value("ok", false)) all_ok = false;
        results.push_back(child_resp);
        if (!child_resp.value("ok", false) && mode == "stop_on_error") break;
    }
    response["ok"] = all_ok;
    response["summary"] = {{"count", results.size()}, {"all_ok", all_ok}};
    response["data"] = {{"results", results}};
    return response;
}

json handle_session_action(const json& request, const std::string& action) {
    json response = base_response(request, action);
    SessionManager manager;
    if (action == "session.open" || action == "session.ensure") {
        std::vector<std::string> args = target_dbdir_args(request);
        if (args.empty()) return error_response(request, action, "INVALID_TARGET", "target.dbdir is required");
        SessionEnsureResult result = manager.ensure_session(args, request_session_name(request), request_transport_options(request));
        if (!result.ok) return error_response(request, action, ensure_error_code(result), result.message);
        response["session"] = session_to_json(result.info);
        response["session"]["reused"] = result.reused;
        response["session"]["healthy"] = true;
        response["summary"] = {{"id", result.session_id}, {"session_id", result.session_id},
                               {"status", result.status}, {"reused", result.reused}};
        response["data"] = {{"session", response["session"]}};
        return response;
    }
    if (action == "session.list") {
        json sessions = json::array();
        for (const auto& s : manager.list_sessions()) sessions.push_back(session_to_json(s));
        response["summary"] = {{"count", sessions.size()}};
        response["data"] = {{"sessions", sessions}};
        return response;
    }
    if (action == "session.doctor") {
        json target = request.value("target", json::object());
        json args = request.value("args", json::object());
        std::string sid;
        if (target.contains("session_id")) sid = json_session_id(target["session_id"]);
        if (sid.empty() && args.contains("session_id")) sid = json_session_id(args["session_id"]);
        if (sid.empty()) return error_response(request, action, "MISSING_FIELD", "target.session_id or args.session_id string is required");
        SessionHealth h = manager.diagnose_session(sid);
        response["ok"] = h.healthy;
        response["session"] = session_to_json(h.info);
        response["summary"] = {{"id", sid}, {"session_id", sid}, {"healthy", h.healthy},
            {"status", session_health_status_name(h.status)}, {"message", h.message}};
        response["data"] = {{"health", response["summary"]}};
        if (!h.healthy) response["error"] = {{"code", "SESSION_UNHEALTHY"}, {"message", h.message},
            {"recoverable", true}, {"candidates", json::array()}, {"suggested_actions", json::array()}};
        return response;
    }
    if (action == "session.kill" || action == "session.close") {
        json args = request.value("args", json::object());
        if (args.value("id", "") == "all") {
            bool ok = manager.kill_all_sessions();
            response["ok"] = ok;
            response["summary"] = {{"target", "all"}, {"killed", ok}};
            return response;
        }
        std::string sid;
        json target = request.value("target", json::object());
        if (target.contains("session_id")) sid = json_session_id(target["session_id"]);
        else if (args.contains("session_id")) sid = json_session_id(args["session_id"]);
        else if (args.contains("id")) sid = json_session_id(args["id"]);
        if (sid.empty()) return error_response(request, action, "MISSING_FIELD", "session id string is required");
        bool ok = manager.kill_session(sid);
        response["ok"] = ok;
        response["summary"] = {{"id", sid}, {"session_id", sid}, {"killed", ok}};
        if (!ok) response["error"] = {{"code", "SESSION_NOT_FOUND"}, {"message", "failed to kill session"},
            {"recoverable", true}, {"candidates", json::array()}, {"suggested_actions", json::array()}};
        return response;
    }
    return error_response(request, action, "UNKNOWN_ACTION", "unknown session action");
}

} // namespace

json schema_payload() {
    return {{"api_version", API_VERSION}, {"request", {{"api_version", API_VERSION}, {"request_id", "optional-id"},
        {"action", "trace.driver"}, {"target", {{"dbdir", "/path/to/simv.daidir"}, {"session_id", nullptr}, {"auto_ensure", true}}},
        {"args", {{"name", "case_a"}, {"transport", "uds"}, {"bind_host", "127.0.0.1"}, {"port", 0}}},
        {"limits", {{"max_results", 50}, {"max_depth", 1}, {"max_paths", 10}, {"timeout_ms", 5000}}},
        {"output", {{"verbosity", "compact"}, {"pretty", false}}},
        {"include_switches", {{"design", json::array({"include_source", "include_ast", "include_candidates",
            "include_trace", "include_expanded_queries", "include_raw_edges", "include_graph", "include_debug"})}}}}},
        {"response", {{"ok", true}, {"action", "trace.driver"}, {"tool", {{"name", "xdebug_design"}, {"version", TOOL_VERSION}}},
            {"session", json::object()}, {"summary", json::object()}, {"data", json::object()}, {"findings", json::array()},
            {"suggested_next_actions", json::array()}, {"warnings", json::array()}, {"error", nullptr}, {"meta", json::object()}}},
        {"transport", {{"default", "uds"}, {"env_default", "XDEBUG_TRANSPORT"}, {"values", json::array({"uds", "tcp", "file"})},
            {"tcp", "session.open/session.ensure accept args.transport=tcp with optional bind_host/host/port. port 0 or omitted lets the server bind an automatically assigned port and write it to endpoint.json."},
            {"file", "session.open/session.ensure accept args.transport=file. The daemon exchanges requests and responses through the session transport directory under ~/.xdebug."}}}};
}

json actions_payload() {
    json implemented = json::array({"session.open", "session.ensure", "session.list", "session.doctor", "session.kill", "session.close",
        "trace.driver", "trace.load", "trace.query", "signal.resolve", "signal.canonicalize",
        "trace.expand", "trace.graph", "trace.path", "trace.explain", "control.explain", "source.context",
        "expr.normalize", "procedural.assignment", "sequential.update", "fsm.explain", "counter.explain",
        "port.trace", "instance.map", "interface.resolve", "batch"});
    return {{"api_version", API_VERSION}, {"implemented", implemented}, {"experimental", json::array()}};
}

namespace {

std::string log_session_id(const json& request) {
    json target = request.value("target", json::object());
    json args = request.value("args", json::object());
    if (target.contains("session_id") && target["session_id"].is_string()) return target["session_id"].get<std::string>();
    if (args.contains("session_id") && args["session_id"].is_string()) return args["session_id"].get<std::string>();
    if (args.contains("name") && args["name"].is_string()) return args["name"].get<std::string>();
    if (target.contains("name") && target["name"].is_string()) return target["name"].get<std::string>();
    return "adhoc";
}

json handle_request_impl(const json& request) {
    std::string action = request.value("action", "");
    std::string api_ver = request.value("api_version", std::string(API_VERSION));
    if (api_ver != API_VERSION && api_ver != "xdebug.v1") {
        return error_response(request, action, "UNSUPPORTED_API_VERSION",
            "expected xdebug.internal.v1 or xdebug.v1", false);
    }
    if (action.empty()) return error_response(request, action, "MISSING_FIELD", "action is required");
    if (action == "batch") return run_batch(request);
    if (starts_with(action, "session.")) return handle_session_action(request, action);
    if (action == "trace.driver") return run_trace_action(request, "driver");
    if (action == "trace.load") return run_trace_action(request, "load");
    if (action == "trace.query") {
        std::string mode = request.value("args", json::object()).value("mode", "driver");
        return run_trace_action(request, mode == "load" ? "load" : "driver");
    }
    if (action == "signal.resolve") return run_signal_resolve_action(request);
    if (action == "signal.canonicalize") return canonicalize_signal(request);
    if (action == "trace.expand" || action == "trace.graph") return trace_expand_like(request, false);
    if (action == "trace.path") return trace_path(request);
    if (action == "trace.explain") return trace_expand_like(request, true);
    if (action == "control.explain") return control_explain(request);
    if (action == "source.context") return source_context(request);
    if (action == "expr.normalize") return run_expr_normalize_action(request);
    if (action == "procedural.assignment") return run_procedural_assignment_action(request);
    if (action == "sequential.update") return run_sequential_update_action(request);
    if (action == "fsm.explain") return run_fsm_explain_action(request);
    if (action == "counter.explain") return run_counter_explain_action(request);
    if (action == "port.trace" || action == "instance.map" || action == "interface.resolve") return run_port_like_action(request, action);

    // All other actions (waveform, combined, etc.): forward to engine server
    // using the same session→socket pattern as design actions.
    json response = base_response(request, action);
    std::string session_id;
    SessionInfo session;
    if (!ensure_target_session(request, response, session_id, session)) return response;
    json args = request.value("args", json::object());
    json result;
    std::string status, message;
    json engine_error;
    if (!send_json_command(session_id, action, args, result, status, message, engine_error)) {
        if (!engine_error.is_null()) {
            response["ok"] = false;
            response["error"] = engine_error;
            return response;
        }
        return error_response(request, action, "SESSION_UNHEALTHY",
            message.empty() ? status : message);
    }
    // send_json_command already extracts the "data" field from the
    // server's ok_response envelope.  result IS the handler payload.
    response["ok"] = true;

    // Build summary: prefer handler-provided summary, then auto-extract
    // top-level scalar fields, then fall back to legacy trace.driver format.
    json result_summary = result.value("summary", json::object());
    if (result_summary.empty()) {
        for (auto it = result.begin(); it != result.end(); ++it) {
            if (it->is_string() || it->is_number() || it->is_boolean())
                result_summary[it.key()] = it.value();
        }
    }
    if (result_summary.empty()) {
        result_summary = {
            {"driver_status", result.value("driver_status", "")},
            {"statement_count", result.value("statement_count", 0)},
            {"root_driver", result.value("root_driver", json::object())}
        };
    }
    response["summary"] = result_summary;
    response["data"] = result;
    if (result.contains("truncated") && result["truncated"].is_boolean())
        response["meta"] = {{"truncated", result["truncated"].get<bool>()}};
    return response;
}

} // namespace

json handle_request(const json& request) {
    using clock = std::chrono::steady_clock;
    const auto begin = clock::now();
    std::string action = request.value("action", "");
    std::string sid = log_session_id(request);
    xdebug_core::log_action_event("backend", "design", sid, action, "begin", true, 0,
                                  {{"request", xdebug_core::request_summary_for_log(request)}});
    json response = handle_request_impl(request);
    long long elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(clock::now() - begin).count();
    bool ok = response.value("ok", false);
    xdebug_core::log_action_event("backend", "design", sid, action, "end", ok, elapsed_ms,
                                  {{"response", xdebug_core::response_summary_for_log(response)},
                                   {"request", ok ? xdebug_core::request_summary_for_log(request) : xdebug_core::sanitize_for_log(request)}});
    return response;
}

} // namespace xdebug_design
