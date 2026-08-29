#pragma once

#include <string>

#include "common/tool_config.h"

namespace xdebug_core {

std::string temporary_dir();
std::string home_dir();
std::string tool_home_dir(const ToolConfig& config);
std::string tool_sessions_dir(const ToolConfig& config);
bool is_valid_session_name(const std::string& session_id);
std::string session_name_rule();
std::string session_dir_name(const std::string& session_id);
std::string tool_session_dir(const ToolConfig& config, const std::string& session_id);
std::string registry_path(const ToolConfig& config);
std::string registry_lock_path(const ToolConfig& config);
std::string socket_path(const ToolConfig& config, const std::string& session_id);
std::string endpoint_path(const ToolConfig& config, const std::string& session_id);
std::string debug_log_path(const ToolConfig& config, const std::string& session_id);
std::string session_json_path(const ToolConfig& config, const std::string& session_id);

} // namespace xdebug_core
