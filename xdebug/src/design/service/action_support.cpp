#include "action_support.h"

#include "../client/client.h"

#include <cctype>
#include <fstream>
#include <sstream>

namespace xdebug_design {

const char* const API_VERSION = "xdebug.internal.v1";
const char* const TOOL_VERSION = "0.1.0";

std::string read_stream(std::istream& in) {
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

std::string read_file(const std::string& path) {
    std::ifstream in(path.c_str());
    if (!in) return "";
    return read_stream(in);
}

std::string trim(const std::string& s) {
    size_t b = 0;
    while (b < s.size() && std::isspace(static_cast<unsigned char>(s[b]))) b++;
    size_t e = s.size();
    while (e > b && std::isspace(static_cast<unsigned char>(s[e - 1]))) e--;
    return s.substr(b, e - b);
}

bool starts_with(const std::string& s, const std::string& prefix) {
    return s.compare(0, prefix.size(), prefix) == 0;
}

std::string leaf_name(const std::string& signal) {
    size_t dot = signal.rfind('.');
    std::string leaf = dot == std::string::npos ? signal : signal.substr(dot + 1);
    size_t bracket = leaf.find('[');
    if (bracket != std::string::npos) leaf = leaf.substr(0, bracket);
    return leaf;
}

std::string lower_copy(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) out.push_back((char)std::tolower((unsigned char)c));
    return out;
}

bool contains_word_like(const std::string& text, const std::string& token) {
    return lower_copy(text).find(lower_copy(token)) != std::string::npos;
}

std::string next_token_after(const std::string& text, const std::string& key) {
    size_t pos = lower_copy(text).find(lower_copy(key));
    if (pos == std::string::npos) return "";
    pos += key.size();
    while (pos < text.size() && std::isspace((unsigned char)text[pos])) pos++;
    size_t begin = pos;
    while (pos < text.size()) {
        char c = text[pos];
        if (!(std::isalnum((unsigned char)c) || c == '_' || c == '.' || c == '[' || c == ']')) break;
        pos++;
    }
    return begin < pos ? text.substr(begin, pos - begin) : "";
}

json session_to_json(const SessionInfo& s) {
    return {
        {"id", s.session_id},
        {"session_id", s.session_id},
        {"dbdir", s.dbdir_path},
        {"dbdir_path", s.dbdir_path},
        {"design_file", s.design_file},
        {"pid", s.server_pid},
        {"transport", s.transport},
        {"socket_path", s.socket_path},
        {"file_dir", s.file_dir},
        {"host", s.host},
        {"bind_host", s.bind_host},
        {"port", s.port},
        {"server_host", s.server_host},
        {"created_at", static_cast<long long>(s.created_at)},
        {"last_active", static_cast<long long>(s.last_active)},
        {"dbdir_mtime", s.dbdir_mtime},
        {"dbdir_size", s.dbdir_size},
        {"dbdir_dev", s.dbdir_dev},
        {"dbdir_inode", s.dbdir_inode}
    };
}

SessionTransportOptions request_transport_options(const json& request) {
    SessionTransportOptions transport;
    const json target = request.value("target", json::object());
    const json args = request.value("args", json::object());
    transport.transport = args.value("transport", target.value("transport", std::string()));
    transport.bind_host = args.value("bind_host", args.value("bind", target.value("bind_host", target.value("bind", std::string()))));
    transport.host = args.value("host", target.value("host", std::string()));
    transport.port = args.value("port", target.value("port", 0));
    return transport;
}

json base_response(const json& request, const std::string& action) {
    json response;
    response["api_version"] = API_VERSION;
    response["request_id"] = request.value("request_id", "");
    response["ok"] = true;
    response["action"] = action;
    response["tool"] = {{"name", "xdebug_design"}, {"version", TOOL_VERSION}};
    response["session"] = nullptr;
    response["summary"] = json::object();
    response["data"] = json::object();
    response["findings"] = json::array();
    response["suggested_next_actions"] = json::array();
    response["warnings"] = json::array();
    response["error"] = nullptr;
    response["meta"] = {{"elapsed_ms", nullptr}, {"truncated", false}};
    return response;
}

std::string response_verbosity(const json& request) {
    json output = request.value("output", json::object());
    if (!output.is_object()) return "compact";
    std::string verbosity = output.value("verbosity", std::string("compact"));
    verbosity = lower_copy(verbosity);
    if (verbosity == "full" || verbosity == "debug") return verbosity;
    return "compact";
}

bool compact_mode(const json& request) {
    std::string verbosity = response_verbosity(request);
    return verbosity != "full" && verbosity != "debug";
}

bool include_arg(const json& request, const std::string& key) {
    json args = request.value("args", json::object());
    if (args.is_object() && args.value(key, false)) return true;
    json output = request.value("output", json::object());
    return output.is_object() && output.value(key, false);
}

int max_examples_arg(const json& request, int def) {
    json args = request.value("args", json::object());
    json limits = request.value("limits", json::object());
    int value = args.value("max_examples", limits.value("max_examples", def));
    return value >= 0 ? value : def;
}

json error_response(const json& request,
                    const std::string& action,
                    const std::string& code,
                    const std::string& message,
                    bool recoverable,
                    const json& candidates,
                    const json& suggested_actions) {
    json response = base_response(request, action);
    response["ok"] = false;
    response["data"] = nullptr;
    response["error"] = {
        {"code", code},
        {"message", message},
        {"recoverable", recoverable},
        {"candidates", candidates},
        {"suggested_actions", suggested_actions}
    };
    response["suggested_next_actions"] = suggested_actions;
    return response;
}

std::vector<std::string> target_dbdir_args(const json& request) {
    std::vector<std::string> args;
    if (!request.contains("target") || !request["target"].is_object()) return args;
    const json& target = request["target"];
    std::string dbdir = target.value("dbdir", target.value("daidir", ""));
    if (!dbdir.empty()) {
        args.push_back("-dbdir");
        args.push_back(dbdir);
    }
    std::string fsdb = target.value("fsdb", "");
    if (!fsdb.empty()) {
        args.push_back("-fsdb");
        args.push_back(fsdb);
    }
    return args;
}

std::string json_session_id(const json& value) {
    return value.is_string() ? value.get<std::string>() : "";
}

std::string request_session_name(const json& request) {
    const json target = request.value("target", json::object());
    const json args = request.value("args", json::object());
    if (args.contains("name") && args["name"].is_string()) return args["name"].get<std::string>();
    if (target.contains("name") && target["name"].is_string()) return target["name"].get<std::string>();
    return "";
}

std::string ensure_error_code(const SessionEnsureResult& result) {
    if (result.status == "session_id_exists") return "SESSION_ID_EXISTS";
    if (result.status == "invalid_session_id") return "INVALID_SESSION_ID";
    if (result.status == "invalid_args") return "INVALID_REQUEST";
    return "SESSION_UNHEALTHY";
}

bool ensure_target_session(const json& request,
                           json& response,
                           std::string& session_id,
                           SessionInfo& session,
                           bool) {
    SessionManager manager;
    const json target = request.value("target", json::object());
    if (target.contains("session_id") && target["session_id"].is_string()) {
        session_id = target["session_id"].get<std::string>();
        if (!manager.get_session(session_id, session)) {
            SessionHealth health = manager.diagnose_session(session_id);
            response = error_response(request, request.value("action", ""), "SESSION_NOT_FOUND",
                                      health.message.empty() ? "session not found" : health.message);
            return false;
        }
        response["session"] = session_to_json(session);
        return true;
    }
    std::vector<std::string> design_args = target_dbdir_args(request);
    if (!design_args.empty()) {
        if (!target.value("auto_ensure", true)) {
            response = error_response(request, request.value("action", ""), "INVALID_TARGET",
                                      "target.dbdir requires auto_ensure=true or an existing session_id");
            return false;
        }
        SessionEnsureResult ensured = manager.ensure_session(design_args, request_session_name(request), request_transport_options(request));
        if (!ensured.ok) {
            response = error_response(request, request.value("action", ""), ensure_error_code(ensured),
                                      ensured.message.empty() ? "failed to ensure session" : ensured.message);
            return false;
        }
        session_id = ensured.session_id;
        session = ensured.info;
        response["session"] = session_to_json(session);
        response["session"]["reused"] = ensured.reused;
        response["session"]["healthy"] = true;
        return true;
    }
    response = error_response(request, request.value("action", ""), "INVALID_TARGET",
                              "target must contain string session_id or dbdir with args.name");
    return false;
}

std::string option_string_from_limits_args(const json& request) {
    std::string options;
    const json args = request.value("args", json::object());
    const json limits = request.value("limits", json::object());
    int limit = 0;
    if (limits.contains("max_results")) limit = limits.value("max_results", 0);
    if (limits.contains("max_rows") && limit <= 0) limit = limits.value("max_rows", 0);
    if (args.contains("limit") && args["limit"].is_number_integer()) limit = args["limit"].get<int>();
    if (limit > 0) options += " --limit " + std::to_string(limit);
    std::string role = args.value("role", "");
    if (!role.empty()) options += " --role " + role;
    bool no_statement_only = args.value("no_statement_only", false);
    if (args.contains("include_statement_only") && args["include_statement_only"].is_boolean()) {
        no_statement_only = !args["include_statement_only"].get<bool>();
    }
    if (no_statement_only) options += " --no-statement-only";
    return options;
}

bool send_json_command(const std::string& session_id,
                       const std::string& action,
                       const json& args,
                       json& parsed,
                       std::string& error_status,
                       std::string& error_message,
                       json& engine_error) {
    json request = {{"api_version", API_VERSION}, {"action", action}, {"args", args}};
    return send_request_capture(session_id, request, parsed, error_status, error_message, engine_error);
}

} // namespace xdebug_design
