#pragma once

#include <string>
#include "json.hpp"

namespace xdebug_design {

using Json = nlohmann::json;

int session_connect(const std::string& session_id);

bool send_request_capture(const std::string& session_id,
                          const Json& request,
                          Json& data,
                          std::string& status,
                          std::string& message,
                          Json& engine_error);
bool session_ping(const std::string& session_id);

} // namespace xdebug_design
