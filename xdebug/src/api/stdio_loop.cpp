#include "api/stdio_loop.h"

#include "api/dispatcher.h"
#include "api/request_parser.h"
#include "api/response.h"
#include "api/xout_renderer.h"
#include "logging/action_log.h"

#include <iostream>
#include <string>
#include <unistd.h>

namespace xdebug {

namespace {

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

bool write_jsonl(const Json& obj) {
    std::cout << obj.dump() << "\n" << std::flush;
    return std::cout.good();
}

Json ready_envelope(int pid) {
    return {
        {"type", "ready"},
        {"protocol", "xdebug-stdio-loop"},
        {"version", 1},
        {"pid", pid},
    };
}

Json quit_envelope(const std::string& id) {
    return {
        {"id", id},
        {"ok", true},
        {"payload_format", "json"},
        {"json", {{"ok", true}, {"action", "stdio.quit"}}},
    };
}

Json loop_error(const std::string& id, const std::string& code, const std::string& message) {
    return {
        {"id", id},
        {"ok", false},
        {"error", {{"code", code}, {"message", message}}},
    };
}

std::string request_id_or_seq(const Json& req, int seq) {
    if (req.contains("request_id") && req["request_id"].is_string()) {
        return req["request_id"].get<std::string>();
    }
    if (req.contains("id") && req["id"].is_string()) {
        return req["id"].get<std::string>();
    }
    return "req-" + std::to_string(seq);
}

bool has_string(const Json& object, const char* key) {
    return object.is_object() && object.contains(key) && object[key].is_string() &&
           !object[key].get<std::string>().empty();
}

std::string log_session_id(const Json& req) {
    Json target = req.value("target", Json::object());
    Json args = req.value("args", Json::object());
    if (has_string(target, "session_id")) return target["session_id"].get<std::string>();
    if (has_string(args, "session_id")) return args["session_id"].get<std::string>();
    if (has_string(args, "id") && args["id"].get<std::string>() != "all") return args["id"].get<std::string>();
    if (has_string(args, "name")) return args["name"].get<std::string>();
    if (has_string(target, "name")) return target["name"].get<std::string>();
    return "adhoc";
}

Json stdio_context(const Json& req, const std::string& id, int seq) {
    Json ctx = {
        {"request_id", id},
        {"seq", seq},
        {"request", xdebug_core::request_summary_for_log(req)}
    };
    std::string action = req.value("action", std::string());
    if (!action.empty()) ctx["action"] = action;
    if (req.contains("trace_id")) ctx["trace_id"] = req["trace_id"];
    if (req.contains("span_id")) ctx["span_id"] = req["span_id"];
    if (req.contains("parent_span_id")) ctx["parent_span_id"] = req["parent_span_id"];
    return ctx;
}

void log_stdout_write_failed(const std::string& session_id, const Json& context) {
    xdebug_core::log_stdio_event(session_id, "loop.stdout_write_failed", false, context);
}

bool request_wants_json(const Json& req, bool default_json) {
    if (req.contains("__xverif_loop_payload_format") &&
        req["__xverif_loop_payload_format"].is_string()) {
        const std::string format = req["__xverif_loop_payload_format"].get<std::string>();
        if (format == "json") return true;
        if (format == "xout") return false;
    }
    if (default_json) return true;
    return false;
}

void strip_loop_internal_fields(Json& req) {
    req.erase("__xverif_loop_payload_format");
}

Json make_envelope(const std::string& id, const Json& req, const Json& rsp, bool default_json) {
    Json out;
    out["id"] = id;
    out["ok"] = rsp.value("ok", false);

    if (!rsp.value("ok", false)) {
        out["error"] = rsp.value("error", Json::object());
        out["json"] = rsp;
        if (!request_wants_json(req, default_json)) {
            out["payload_format"] = "xout";
            out["xout"] = render_xout_response(rsp);
        } else {
            out["payload_format"] = "json";
        }
        return out;
    }

    if (request_wants_json(req, default_json)) {
        out["payload_format"] = "json";
        out["json"] = rsp;
    } else {
        out["payload_format"] = "xout";
        out["xout"] = render_xout_response(rsp);
    }

    return out;
}

} // namespace

// ---------------------------------------------------------------------------
// main loop
// ---------------------------------------------------------------------------

int run_stdio_loop(const std::string& executable_dir, bool default_json) {
    Dispatcher dispatcher(executable_dir);

    // Announce the loop is ready
    Json ready = ready_envelope(static_cast<int>(getpid()));
    bool ready_written = write_jsonl(ready);
    xdebug_core::log_stdio_event("adhoc", "loop.ready", ready_written,
                                 {{"pid", static_cast<int>(getpid())}});
    if (!ready_written) {
        log_stdout_write_failed("adhoc", {{"phase", "loop.ready"}});
    }

    std::string line;
    int seq = 0;

    while (std::getline(std::cin, line)) {
        ++seq;
        if (line.empty()) continue;

        // Parse the JSON request
        Json req;
        std::string error;
        if (!parse_request_text(line, req, error)) {
            const std::string id = "req-" + std::to_string(seq);
            Json ctx = {{"request_id", id}, {"seq", seq}, {"line_size", line.size()}, {"error", error}};
            Json err = loop_error(id, "INVALID_JSON", error);
            bool written = write_jsonl(err);
            xdebug_core::log_stdio_event("adhoc", "loop.invalid_json", false, ctx);
            if (!written) log_stdout_write_failed("adhoc", ctx);
            continue;
        }

        const std::string id = request_id_or_seq(req, seq);
        const bool wants_json = request_wants_json(req, default_json);
        strip_loop_internal_fields(req);
        const std::string action = req.value("action", std::string());
        const std::string sid = log_session_id(req);
        Json base_ctx = stdio_context(req, id, seq);
        xdebug_core::log_stdio_event(sid, "request.begin", true, base_ctx);

        // Handle quit
        if (action == "stdio.quit") {
            Json rsp = quit_envelope(id);
            bool written = write_jsonl(rsp);
            xdebug_core::log_stdio_event(sid, "loop.quit", written, base_ctx);
            xdebug_core::log_stdio_event(sid, "request.end", written,
                                         {{"request_id", id}, {"seq", seq}, {"action", action},
                                          {"response", {{"ok", true}, {"action", action}}}});
            if (!written) log_stdout_write_failed(sid, base_ctx);
            return 0;
        }

        // Validate
        std::string validated_action;
        if (!validate_request(req, validated_action, error)) {
            const std::string code =
                req.value("api_version", std::string()) == kApiVersion
                    ? "INVALID_REQUEST"
                    : "UNSUPPORTED_API_VERSION";

            Json rsp = make_error(req, req.value("action", std::string()), code, error, false);
            Json envelope = make_envelope(id, req, rsp, wants_json);
            bool written = write_jsonl(envelope);
            Json ctx = base_ctx;
            ctx["error"] = {{"code", code}, {"message", error}};
            xdebug_core::log_stdio_event(sid, "loop.validate_failed", false, ctx);
            xdebug_core::log_stdio_event(sid, "request.end", false,
                                         {{"request_id", id}, {"seq", seq}, {"action", action},
                                          {"response", xdebug_core::response_summary_for_log(rsp)}});
            if (!written) log_stdout_write_failed(sid, ctx);
            continue;
        }

        // Dispatch
        Json rsp = dispatcher.dispatch(req);
        Json envelope = make_envelope(id, req, rsp, wants_json);
        bool written = write_jsonl(envelope);
        xdebug_core::log_stdio_event(log_session_id(req), "request.end",
                                     written && rsp.value("ok", false),
                                     {{"request_id", id}, {"seq", seq}, {"action", action},
                                      {"response", xdebug_core::response_summary_for_log(rsp)}});
        if (!written) log_stdout_write_failed(sid, base_ctx);
    }

    xdebug_core::log_stdio_event("adhoc", "loop.stdin_eof", true,
                                 {{"seq", seq}, {"pid", static_cast<int>(getpid())}});
    return 0;
}

} // namespace xdebug
