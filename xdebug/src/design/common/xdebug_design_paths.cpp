#include "xdebug_design_paths.h"

#include <cstdio>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include "common/path_utils.h"

namespace xdebug_design {

namespace {

const xdebug_core::ToolConfig& tool_config() {
    static const xdebug_core::ToolConfig config =
        xdebug_core::make_tool_config("xdebug-engine", ".xdebug/engine", "xdebug-engine", "1.2");
    return config;
}

std::string xdebug_home_dir() {
    return xdebug_core::home_dir() + "/.xdebug";
}

bool ensure_dir(const std::string& path) {
    if (mkdir(path.c_str(), 0700) == 0) return true;
    struct stat st;
    return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

bool remove_file_if_exists(const std::string& path) {
    if (unlink(path.c_str()) == 0) return true;
    return access(path.c_str(), F_OK) != 0;
}

} // namespace

std::string xdebug_design_home_dir() {
    return xdebug_core::tool_home_dir(tool_config());
}

std::string xdebug_design_sessions_dir() {
    return xdebug_core::tool_sessions_dir(tool_config());
}

std::string session_dir_name(const std::string& session_id) {
    return xdebug_core::session_dir_name(session_id);
}

std::string xdebug_design_session_dir(const std::string& session_id) {
    return xdebug_core::tool_session_dir(tool_config(), session_id);
}

std::string xdebug_design_registry_path() {
    return xdebug_core::registry_path(tool_config());
}

std::string xdebug_design_registry_lock_path() {
    return xdebug_core::registry_lock_path(tool_config());
}

std::string xdebug_design_session_json_path(const std::string& session_id) {
    return xdebug_core::session_json_path(tool_config(), session_id);
}

std::string xdebug_design_socket_path(const std::string& session_id) {
    return xdebug_core::socket_path(tool_config(), session_id);
}

std::string xdebug_design_endpoint_path(const std::string& session_id) {
    return xdebug_core::endpoint_path(tool_config(), session_id);
}

std::string xdebug_design_debug_log_path(const std::string& session_id) {
    return xdebug_core::debug_log_path(tool_config(), session_id);
}

std::string xdebug_design_legacy_registry_path() {
    return xdebug_home_dir() + "/design/legacy.registry";
}

bool xdebug_design_ensure_home() {
    bool ok = ensure_dir(xdebug_home_dir()) &&
              ensure_dir(xdebug_design_home_dir()) &&
              ensure_dir(xdebug_design_sessions_dir());
    if (ok) {
        int fd = open(xdebug_design_registry_lock_path().c_str(), O_RDWR | O_CREAT, 0600);
        if (fd >= 0) close(fd);
    }
    return ok;
}

bool xdebug_design_ensure_session_dir(const std::string& session_id) {
    return xdebug_design_ensure_home() && ensure_dir(xdebug_design_session_dir(session_id));
}

bool xdebug_design_remove_session_dir(const std::string& session_id) {
    std::string dir = xdebug_design_session_dir(session_id);
    remove_file_if_exists(dir + "/session.json");
    remove_file_if_exists(dir + "/socket");
    remove_file_if_exists(dir + "/endpoint.json");
    // Preserve debug.log and logs/ for post-failure diagnostics.
    return true;
}

} // namespace xdebug_design
