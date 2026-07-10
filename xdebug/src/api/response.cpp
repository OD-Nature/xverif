#include "api/response.h"
#include "core/diagnostic_error.h"

namespace xdebug {

Json make_response(const Json& request, const std::string& action, bool ok) {
    Json response;
    response["api_version"] = kApiVersion;
    if (request.contains("request_id")) response["request_id"] = request["request_id"];
    response["ok"] = ok;
    response["action"] = action;
    response["tool"] = {{"name", "xdebug"}, {"version", kToolVersion}};
    response["session"] = nullptr;
    response["summary"] = Json::object();
    response["data"] = ok ? Json::object() : Json(nullptr);
    response["error"] = nullptr;
    return response;
}

Json make_error(const Json& request,
                const std::string& action,
                const std::string& code,
                const std::string& message,
                bool recoverable) {
    Json response = make_response(request, action, false);
    response["error"] = {
        {"code", code},
        {"message", message},
        {"recoverable", recoverable},
        {"error_layer", recoverable ? "handler" : "internal"}
    };
    response["summary"] = {{"status", "error"}, {"error_code", code}};
    return response;
}

Json make_error(const Json& request,
                const std::string& action,
                const Json& error) {
    Json response = make_response(request, action, false);
    Json normalized = xdebug_core::normalize_diagnostic_error(error, "handler");
    if (!normalized.contains("code")) normalized["code"] = "ACTION_FAILED";
    if (!normalized.contains("message")) normalized["message"] = "action failed";
    response["error"] = normalized;
    response["summary"] = {
        {"status", "error"},
        {"error_code", normalized.value("code", std::string("ACTION_FAILED"))}
    };
    return response;
}

Json normalize_engine_response(const Json& engine_response) {
    Json response = engine_response;
    response["api_version"] = kApiVersion;
    if (response.contains("tool") && response["tool"].is_object()) {
        response["tool"]["name"] = "xdebug";
        response["tool"]["version"] = kToolVersion;
    }
    if (response.contains("suggested_next_actions") &&
        response["suggested_next_actions"].is_array()) {
        for (auto& next : response["suggested_next_actions"]) {
            if (next.is_object() && next.contains("tool")) next["tool"] = "xdebug";
        }
    }
    return response;
}

} // namespace xdebug
