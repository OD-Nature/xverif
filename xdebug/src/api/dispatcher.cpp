#include "api/dispatcher.h"
#include "api/action_catalog.h"
#include "api/action_registry_init.h"
#include "api/request_envelope.h"
#include "api/request_validator.h"
#include "api/resource_resolver.h"
#include "api/response.h"
#include "logging/action_log.h"

#include <chrono>
#include <limits.h>
#include <string>
#include <unistd.h>

namespace xdebug {

namespace {

bool has_string(const Json& object, const char* key) {
    return object.contains(key) && object[key].is_string() &&
           !object[key].get<std::string>().empty();
}

std::string requested_name(const Json& request) {
    Json args = request.value("args", Json::object());
    Json target = request.value("target", Json::object());
    if (has_string(args, "name")) return args["name"].get<std::string>();
    if (has_string(target, "name")) return target["name"].get<std::string>();
    return "";
}

Json engine_error(const Json& request, const std::string& action, const std::string& message) {
    return make_error(request, action, "INTERNAL_ENGINE_FAILED", message);
}

bool backend_cleanup_ok(const Json& response) {
    if (response.value("ok", false)) return true;
    Json error = response.value("error", Json::object());
    std::string code = error.value("code", std::string());
    return code == "SESSION_NOT_FOUND" || code == "SESSION_UNHEALTHY";
}

std::string stable_resource_path(const std::string& path) {
    if (path.empty() || path[0] == '/') return path;
    char cwd[PATH_MAX] = {};
    return getcwd(cwd, sizeof(cwd)) ? std::string(cwd) + "/" + path : path;
}

void stabilize_resource_paths(Json& target) {
    if (has_string(target, "daidir")) {
        target["daidir"] = stable_resource_path(target["daidir"].get<std::string>());
    }
    if (has_string(target, "fsdb")) {
        target["fsdb"] = stable_resource_path(target["fsdb"].get<std::string>());
    }
}

std::string request_log_session_id(const Json& request, const Json& response = Json()) {
    Json target = request.value("target", Json::object());
    Json args = request.value("args", Json::object());
    if (has_string(target, "session_id")) return target["session_id"].get<std::string>();
    if (has_string(args, "session_id")) return args["session_id"].get<std::string>();
    if (has_string(args, "id") && args["id"].get<std::string>() != "all") return args["id"].get<std::string>();
    if (has_string(args, "name")) return args["name"].get<std::string>();
    if (has_string(target, "name")) return target["name"].get<std::string>();
    if (response.is_object()) {
        Json session = response.value("session", Json::object());
        if (has_string(session, "id")) return session["id"].get<std::string>();
        if (has_string(session, "session_id")) return session["session_id"].get<std::string>();
        Json summary = response.value("summary", Json::object());
        if (has_string(summary, "session_id")) return summary["session_id"].get<std::string>();
        if (has_string(summary, "id")) return summary["id"].get<std::string>();
    }
    return "adhoc";
}

std::string target_mode_for_log(const Json& request, const Json& response = Json()) {
    Json target = request.value("target", Json::object());
    if (has_string(target, "mode")) return target["mode"].get<std::string>();
    Json summary = response.value("summary", Json::object());
    if (has_string(summary, "mode")) return summary["mode"].get<std::string>();
    bool daidir = has_string(target, "daidir");
    bool fsdb = has_string(target, "fsdb");
    if (daidir && fsdb) return "combined";
    if (daidir) return "design";
    if (fsdb) return "waveform";
    return "";
}

} // namespace

Dispatcher::Dispatcher(const std::string& executable_dir)
    : adapter_(executable_dir) {}

std::string Dispatcher::mode_for_target(const Json& target) const {
    const bool daidir = has_string(target, "daidir");
    const bool fsdb = has_string(target, "fsdb");
    if (daidir && fsdb) return "combined";
    if (daidir) return "design";
    if (fsdb) return "waveform";
    return "";
}

Json Dispatcher::resolve_target(const Json& request) const {
    Json target = request.value("target", Json::object());
    if (has_string(target, "session_id")) {
        SessionRecord record;
        if (sessions_.get(target["session_id"].get<std::string>(), record)) {
            if (!record.daidir.empty()) target["daidir"] = record.daidir;
            if (!record.fsdb.empty()) target["fsdb"] = record.fsdb;
            target["mode"] = record.mode;
        }
    }
    stabilize_resource_paths(target);
    return target;
}

Json Dispatcher::forward_action(const Json& request) {
    Json forwarded = request;
    Json target = forwarded.value("target", Json::object());
    Json args = forwarded.value("args", Json::object());
    if (!has_string(target, "session_id") && has_string(args, "name") && !has_string(target, "name")) {
        target["name"] = args["name"];
    }
    forwarded["target"] = target;
    Json response;
    std::string error;
    if (!adapter_.invoke(forwarded, response, error)) {
        return engine_error(request, request.value("action", std::string()), error);
    }
    return response;
}

Json Dispatcher::resource_error(const Json& request, const ActionSpec& spec, const Json& target) const {
    RequestEnvelope envelope = RequestEnvelope::from_json(request);
    envelope.target = target;
    ResourceResolver resolver;
    ResourceResolution resolution = resolver.resolve(envelope, spec);
    if (resolution.ok) return Json();
    return make_error(request, spec.name, resolution.code, resolution.message);
}

Json Dispatcher::handle_engine_forward(const Json& request, const ActionSpec& spec) {
    Json target = resolve_target(request);
    Json err_resp = resource_error(request, spec, target);
    if (!err_resp.is_null()) return err_resp;
    Json routed = request;
    routed["target"] = target;
    Json response = forward_action(routed);
    // Auto-register session for ad-hoc queries (no session_id).
    if (response.value("ok", false) && !has_string(target, "session_id") &&
        !requested_name(request).empty()) {
        SessionRecord record;
        record.id = requested_name(request);
        record.mode = mode_for_target(target);
        record.daidir = target.value("daidir", std::string());
        record.fsdb = target.value("fsdb", std::string());
        sessions_.put(record);
        xdebug_core::update_public_session_manifest(record.id, record.mode, record.daidir, record.fsdb);
    }
    return response;
}

Json Dispatcher::handle_batch(const Json& request) {
    Json requests = request.value("args", Json::object()).value("requests", Json::array());
    if (!requests.is_array()) {
        return make_error(request, "batch", "MISSING_FIELD", "args.requests[] is required");
    }
    Json response = make_response(request, "batch");
    Json results = Json::array();
    bool all_ok = true;
    std::string mode = request.value("args", Json::object()).value("mode", std::string("continue_on_error"));
    for (auto child : requests) {
        if (!child.contains("api_version")) child["api_version"] = kApiVersion;
        Json result = dispatch(child);
        results.push_back(result);
        if (!result.value("ok", false)) {
            all_ok = false;
            if (mode == "stop_on_error") break;
        }
    }
    response["ok"] = all_ok;
    response["summary"] = {{"count", results.size()}, {"all_ok", all_ok}};
    response["data"] = {{"results", results}};
    if (!all_ok) response["error"] = {{"code", "BATCH_PARTIAL_FAILURE"}, {"message", "one or more child requests failed"}, {"recoverable", true}};
    return response;
}

Json Dispatcher::handle_session(const Json& request, const std::string& action) {
    Json target = resolve_target(request);
    Json args = request.value("args", Json::object());
    if (action == "session.list") {
        Json response = make_response(request, action);
        Json records = Json::array();
        for (const auto& record : sessions_.list()) records.push_back(session_record_json(record));
        response["summary"] = {{"session_count", records.size()}};
        response["data"] = {{"sessions", records}};
        return response;
    }
    if (action == "session.gc") {
        Json before = Json::array();
        for (const auto& record : sessions_.list()) before.push_back(session_record_json(record));
        Json removed = Json::array();
        Json kept = Json::array();
        for (const auto& record : sessions_.list()) {
            Json doctor_req = request;
            doctor_req["action"] = "session.doctor";
            doctor_req["target"] = {{"session_id", record.id}};
            Json health = forward_action(doctor_req);
            bool healthy = health.value("ok", false);
            if (healthy) {
                kept.push_back({{"session_id", record.id}, {"mode", record.mode}});
            } else {
                Json kill_req = request;
                kill_req["action"] = "session.kill";
                kill_req["target"] = {{"session_id", record.id}};
                kill_req["args"] = Json::object();
                Json kill_result = handle_session(kill_req, "session.kill");
                removed.push_back({{"session_id", record.id}, {"mode", record.mode},
                                   {"reason", "unhealthy"}, {"health", health},
                                   {"kill_ok", kill_result.value("ok", false)}});
            }
        }
        Json response = make_response(request, action);
        response["summary"] = {{"status", "completed"},
                               {"before_count", before.size()},
                               {"kept_count", kept.size()},
                               {"removed_count", removed.size()}};
        response["data"] = {{"before", before}, {"kept", kept}, {"removed", removed}};
        return response;
    }
    if (action == "session.open" || action == "session.ensure") {
        const std::string name = requested_name(request);
        const std::string mode = mode_for_target(target);
        if (name.empty()) return make_error(request, action, "MISSING_FIELD", "args.name is required");
        if (mode.empty()) return make_error(request, action, "RESOURCE_REQUIRED", "target.daidir or target.fsdb is required");
        SessionRecord existing;
        bool reopened_existing = false;
        if (sessions_.get(name, existing)) {
            const bool reopen = action == "session.open" && args.value("reopen", false);
            const bool reuse = args.value("reuse", false) || action == "session.ensure";
            const bool resource_match = existing.mode == mode &&
                (mode == "design" || existing.daidir == target.value("daidir", std::string())) &&
                (mode == "waveform" || existing.fsdb == target.value("fsdb", std::string()));
            if (reopen) {
                Json kill_req = request;
                kill_req["action"] = "session.kill";
                kill_req["target"] = {{"session_id", name}};
                kill_req["args"] = Json::object();
                Json kill_result = handle_session(kill_req, "session.kill");
                if (!kill_result.value("ok", false)) return kill_result;
                reopened_existing = true;
            } else if (reuse && resource_match) {
                Json doctor_req = request;
                doctor_req["action"] = "session.doctor";
                doctor_req["target"] = {{"session_id", name}};
                Json health = forward_action(doctor_req);
                bool healthy = health.value("ok", false);
                if (healthy) {
                    xdebug_core::update_public_session_manifest(existing.id, existing.mode, existing.daidir, existing.fsdb);
                    Json response = make_response(request, action);
                    response["session"] = session_record_json(existing);
                    response["summary"] = {{"session_id", name}, {"mode", mode}, {"reused", true}, {"healthy", true}};
                    response["data"] = {{"session", response["session"]}, {"health", health}};
                    return response;
                }
                Json kill_req = request;
                kill_req["action"] = "session.kill";
                kill_req["target"] = {{"session_id", name}};
                kill_req["args"] = Json::object();
                Json kill_result = handle_session(kill_req, "session.kill");
                if (!kill_result.value("ok", false)) return kill_result;
                reopened_existing = true;
            } else {
                Json err = make_error(request, action, "SESSION_ID_EXISTS",
                                      "session id already exists: " + name + "; pass args.reuse:true to reuse matching healthy sessions or args.reopen:true to replace it");
                err["summary"] = {{"session_id", name}, {"mode", mode}, {"existing", session_record_json(existing)},
                                  {"requested", target}, {"resource_match", resource_match},
                                  {"suggested_args", {{"reuse", true}, {"reopen", true}}}};
                return err;
            }
        }
        // Spawn ONE unified engine (handles design, waveform, or both).
        Json open_request = request;
        open_request["action"] = "session.open";
        open_request["target"] = target;
        Json result = forward_action(open_request);
        if (!result.value("ok", false)) return result;
        SessionRecord record;
        record.id = name;
        record.mode = mode;
        record.daidir = target.value("daidir", std::string());
        record.fsdb = target.value("fsdb", std::string());
        if (!sessions_.put(record)) {
            return make_error(request, action, "SESSION_STORE_FAILED", "failed to store xdebug session");
        }
        xdebug_core::update_public_session_manifest(record.id, record.mode, record.daidir, record.fsdb);
        Json response = make_response(request, action);
        response["session"] = session_record_json(record);
        response["summary"] = {{"session_id", name}, {"mode", mode}, {"reused", false}, {"reopened", reopened_existing}};
        response["data"] = {{"session", response["session"]}};
        return response;
    }
    std::string id = target.value("session_id", args.value("session_id", args.value("id", std::string())));
    if (id == "all") {
        Json results = Json::array();
        int removed_count = 0;
        for (const auto& record : sessions_.list()) {
            Json kill_req = request;
            kill_req["target"] = {{"session_id", record.id}};
            kill_req["args"] = Json::object();
            Json result = handle_session(kill_req, "session.kill");
            if (result.value("ok", false)) removed_count++;
            results.push_back({{"session_id", record.id}, {"mode", record.mode}, {"result", result}});
        }
        Json response = make_response(request, action);
        response["summary"] = {{"status", "removed"}, {"target", "all"},
                               {"requested_count", results.size()}, {"removed_count", removed_count}};
        response["data"] = {{"results", results}};
        return response;
    }
    if (id.empty()) return make_error(request, action, "MISSING_FIELD", "target.session_id is required");
    SessionRecord record;
    if (!sessions_.get(id, record)) return make_error(request, action, "SESSION_NOT_FOUND", "session not found: " + id);
    if (action == "session.kill" || action == "session.close") {
        Json inner = request;
        inner["action"] = "session.kill";
        inner["target"] = {{"session_id", id}};
        Json r = forward_action(inner);
        bool ok = backend_cleanup_ok(r);
        sessions_.remove(id);
        Json response = make_response(request, action, ok);
        response["summary"] = {{"session_id", id}, {"mode", record.mode}, {"removed", ok}};
        response["data"] = {{"session", session_record_json(record)}, {"backends", r}};
        if (!ok) response["error"] = {{"code", "SESSION_STALE"}, {"message", "session was removed from xdebug registry but backend cleanup failed"}, {"recoverable", true}};
        return response;
    }
    if (action == "session.doctor") {
        Json inner = request;
        inner["target"] = {{"session_id", id}};
        Json health = forward_action(inner);
        Json response = make_response(request, action);
        response["ok"] = health.value("ok", false);
        response["session"] = session_record_json(record);
        response["summary"] = {{"session_id", id}, {"mode", record.mode}, {"healthy", health.value("ok", false)}};
        response["data"] = {{"health", health}};
        if (!response["ok"].get<bool>()) response["error"] = {{"code", "SESSION_UNHEALTHY"}, {"message", "session engine is unhealthy"}, {"recoverable", true}};
        return response;
    }
    return make_error(request, action, "UNKNOWN_ACTION", "unknown session action: " + action);
}

Json Dispatcher::dispatch_impl(const Json& request) {
    const std::string action = request.value("action", std::string());
    const ActionSpec* spec = default_action_registry().find_spec(action);
    if (!spec || spec->status == ActionStatus::Removed) {
        return make_error(request, action, "UNKNOWN_ACTION", "unknown action: " + action);
    }

    RequestEnvelope envelope = RequestEnvelope::from_json(request);
    RequestValidator validator;
    ValidationResult validation = validator.validate(envelope, *spec);
    if (!validation.ok) return make_error(request, action, validation.code, validation.message);

    if (spec->handler_kind == "schema") return catalog_schema_response(request);
    if (spec->handler_kind == "actions") return catalog_actions_response(request);
    if (spec->handler_kind == "batch") return handle_batch(request);
    if (spec->handler_kind == "session") return handle_session(request, action);
    if (spec->handler_kind == "engine_forward") {
        return handle_engine_forward(request, *spec);
    }
    return make_error(request, action, "NOT_IMPLEMENTED", "no handler registered for action: " + action);
}

Json Dispatcher::dispatch(const Json& request) {
    using clock = std::chrono::steady_clock;
    const auto begin = clock::now();
    const std::string action = request.value("action", std::string());
    const std::string begin_session = request_log_session_id(request);
    Json begin_context = {
        {"request", xdebug_core::request_summary_for_log(request)}
    };
    xdebug_core::log_action_event("public", "xdebug", begin_session, action, "begin", true, 0, begin_context);

    Json response;
    try {
        response = dispatch_impl(request);
    } catch (const std::exception& e) {
        response = make_error(request, action, "INTERNAL_ERROR", e.what(), false);
    } catch (...) {
        response = make_error(request, action, "INTERNAL_ERROR", "unhandled exception", false);
    }

    const auto end = clock::now();
    long long elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - begin).count();
    const bool ok = response.value("ok", false);
    const std::string session_id = request_log_session_id(request, response);
    Json context = {
        {"request", xdebug_core::request_summary_for_log(request)},
        {"response", xdebug_core::response_summary_for_log(response)},
        {"mode", target_mode_for_log(request, response)}
    };
    if (!ok) {
        context["request_compact"] = xdebug_core::sanitize_for_log(request);
        context["response_compact"] = xdebug_core::sanitize_for_log(response);
    }
    xdebug_core::log_action_event("public", "xdebug", session_id, action, "end", ok, elapsed_ms, context);
    return response;
}

} // namespace xdebug
