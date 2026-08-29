#include "common/path_utils.h"

#include "common/env_config.h"

#include <iomanip>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>

namespace xdebug_core {

namespace {

unsigned long long stable_path_hash(const std::string& value) {
    unsigned long long hash = 1469598103934665603ULL;
    for (unsigned char c : value) {
        hash ^= static_cast<unsigned long long>(c);
        hash *= 1099511628211ULL;
    }
    return hash;
}

std::string short_socket_path(const std::string& nominal_path) {
    std::ostringstream oss;
    oss << temporary_dir() << "/xdebug-" << static_cast<unsigned long long>(getuid())
        << "-" << std::hex << stable_path_hash(nominal_path) << ".sock";
    return oss.str();
}

std::string safe_dir_prefix(const std::string& session_id) {
    std::string prefix = session_id.substr(0, session_id.size() < 16 ? session_id.size() : 16);
    for (char& c : prefix) {
        const unsigned char u = static_cast<unsigned char>(c);
        if (!((u >= 'A' && u <= 'Z') || (u >= 'a' && u <= 'z') ||
              (u >= '0' && u <= '9') || u == '_')) {
            c = '_';
        }
    }
    return prefix.empty() ? std::string("adhoc") : prefix;
}

}  // namespace

std::string temporary_dir() {
    std::string path = env_raw_string("XVERIF_TEST_TMPDIR");
    if (!path.empty()) {
        mkdir(path.c_str(), 0700);
        return path;
    }
    std::string home = env_raw_string("HOME");
    std::string root = (home.empty() ? std::string(".") : home) + "/.xdebug";
    mkdir(root.c_str(), 0700);
    path = root + "/tmp";
    mkdir(path.c_str(), 0700);
    return path;
}

std::string home_dir() {
    std::string home = env_raw_string("HOME");
    return home.empty() ? temporary_dir() : home;
}

std::string tool_home_dir(const ToolConfig& config) {
    return home_dir() + "/" + config.home_dir_name;
}

std::string tool_sessions_dir(const ToolConfig& config) {
    return tool_home_dir(config) + "/sessions";
}

bool is_valid_session_name(const std::string& session_id) {
    if (session_id.empty() || session_id.size() > 64) return false;
    unsigned char first = static_cast<unsigned char>(session_id.front());
    if (!((first >= 'A' && first <= 'Z') || (first >= 'a' && first <= 'z'))) return false;
    for (unsigned char c : session_id) {
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
              (c >= '0' && c <= '9') || c == '_')) return false;
    }
    return true;
}

std::string session_name_rule() {
    return "session name must start with an ASCII letter and contain only "
           "ASCII letters, digits, and underscores, with maximum length 64";
}

std::string session_dir_name(const std::string& session_id) {
    std::ostringstream oss;
    std::string prefix = safe_dir_prefix(session_id);
    oss << prefix << "_" << std::hex << std::nouppercase << std::setw(16)
        << std::setfill('0') << stable_path_hash(session_id);
    return oss.str();
}

std::string tool_session_dir(const ToolConfig& config, const std::string& session_id) {
    return tool_sessions_dir(config) + "/" + session_dir_name(session_id);
}

std::string registry_path(const ToolConfig& config) {
    return tool_home_dir(config) + "/registry.json";
}

std::string registry_lock_path(const ToolConfig& config) {
    return tool_home_dir(config) + "/registry.lock";
}

std::string socket_path(const ToolConfig& config, const std::string& session_id) {
    const std::string nominal = tool_session_dir(config, session_id) + "/socket";
    // Linux sockaddr_un::sun_path has 108 bytes including the terminating NUL.
    // Keep a little margin and use a deterministic repository-local fallback for long HOME
    // paths commonly produced by pytest and CI workspaces.
    return nominal.size() < 104 ? nominal : short_socket_path(nominal);
}

std::string endpoint_path(const ToolConfig& config, const std::string& session_id) {
    return tool_session_dir(config, session_id) + "/endpoint.json";
}

std::string debug_log_path(const ToolConfig& config, const std::string& session_id) {
    return tool_session_dir(config, session_id) + "/debug.log";
}

std::string session_json_path(const ToolConfig& config, const std::string& session_id) {
    return tool_session_dir(config, session_id) + "/session.json";
}

} // namespace xdebug_core
