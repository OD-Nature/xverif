#include "api/action_catalog.h"
#include "api/action_registry_init.h"
#include "api/response.h"
#include "common/env_config.h"

#include <fstream>
#include <sstream>

namespace xdebug {

namespace {

Json string_array(const std::set<std::string>& values) {
    Json array = Json::array();
    for (const auto& value : values) array.push_back(value);
    return array;
}

std::set<std::string> actions_for_category(const std::string& category) {
    std::set<std::string> out;
    std::vector<ActionSpec> specs = default_action_registry().list_specs(false);
    for (size_t i = 0; i < specs.size(); ++i) {
        if (specs[i].category == category) out.insert(specs[i].name);
    }
    return out;
}

Json action_name_array(bool include_removed) {
    Json out = Json::array();
    std::vector<ActionSpec> specs = default_action_registry().list_specs(include_removed);
    for (size_t i = 0; i < specs.size(); ++i) {
        if (!include_removed && specs[i].status == ActionStatus::Removed) continue;
        if (include_removed && specs[i].status != ActionStatus::Removed) continue;
        out.push_back(specs[i].name);
    }
    return out;
}

std::string schema_root() {
    std::string home = xdebug_core::env_raw_string("XVERIF_HOME");
    if (!home.empty()) return home + "/xdebug/schemas/v1/actions/";
    return "xdebug/schemas/v1/actions/";
}

bool read_json_file(const std::string& path, Json& out) {
    std::ifstream input(path.c_str());
    if (!input.good()) return false;
    try {
        input >> out;
    } catch (...) {
        return false;
    }
    return true;
}

} // namespace

const std::set<std::string>& design_actions() {
    static const std::set<std::string> actions = actions_for_category("design");
    return actions;
}

const std::set<std::string>& waveform_actions() {
    static const std::set<std::string> actions = actions_for_category("waveform");
    return actions;
}

Json catalog_schema_response(const Json& request) {
    Json response = make_response(request, "schema");
    Json args = request.value("args", Json::object());
    std::string action = args.value("action", std::string());
    std::string kind = args.value("kind", std::string());
    if (!action.empty()) {
        if (kind.empty()) kind = "request";
        const ActionSpec* spec = default_action_registry().find_spec(action);
        if (!spec) {
            return make_error(request, "schema", "UNKNOWN_ACTION", "unknown action: " + action);
        }
        std::string rel;
        if (kind == "request") rel = spec->request_schema;
        else if (kind == "response") rel = spec->response_schema;
        else return make_error(request, "schema", "INVALID_REQUEST", "schema args.kind must be request or response");
        const std::string prefix = "schemas/v1/actions/";
        std::string path = rel;
        if (path.compare(0, prefix.size(), prefix) == 0) path = schema_root() + path.substr(prefix.size());
        Json schema;
        if (rel.empty() || !read_json_file(path, schema)) {
            return make_error(request, "schema", "ACTION_SCHEMA_NOT_FOUND", "schema not found for " + action + " " + kind);
        }
        response["summary"] = {{"action", action}, {"kind", kind}};
        response["data"] = {{"schema", schema}, {"schema_path", rel}};
        return response;
    }
    response["data"] = {
        {"api_version", kApiVersion},
        {"request", {
            {"required", Json::array({"api_version", "action"})},
            {"target_resources", Json::array({"daidir", "fsdb", "session_id"})},
            {"modes", Json::array({"design", "waveform", "combined"})}
        }},
        {"combined_action", {
            {"action", "trace.active_driver"},
            {"required_target", Json::array({"daidir", "fsdb"})},
            {"required_args", Json::array({"signal", "time"})},
            {"optional_args", Json::array({"include_control", "include_parity"})}
        }},
        {"contract", {
            {"source", "ActionRegistry"},
            {"schema_root", "xdebug/schemas/v1"},
            {"action_count", default_action_registry().list_specs(false).size()}
        }}
    };
    return response;
}

Json catalog_actions_response(const Json& request) {
    Json response = make_response(request, "actions");
    Json descriptors = default_action_registry().list_descriptors(false);
    Json implemented = action_name_array(false);
    Json removed = action_name_array(true);
    response["summary"] = {
        {"action_count", implemented.size()},
        {"removed_count", removed.size()}
    };
    response["data"] = {
        {"implemented", implemented},
        {"actions", descriptors},
        {"removed", removed},
        {"modes", {
            {"design", string_array(actions_for_category("design"))},
            {"waveform", string_array(actions_for_category("waveform"))},
            {"combined", string_array(actions_for_category("combined"))},
            {"builtin", string_array(actions_for_category("builtin"))},
            {"session", string_array(actions_for_category("session"))}
        }}
    };
    return response;
}

} // namespace xdebug
