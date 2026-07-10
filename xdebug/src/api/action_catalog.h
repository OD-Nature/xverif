#pragma once

#include "api/json_types.h"

#include <set>
#include <string>

namespace xdebug {

const std::set<std::string>& design_actions();
const std::set<std::string>& waveform_actions();
Json catalog_schema_response(const Json& request);
Json catalog_actions_response(const Json& request);
Json suggested_action_names(const std::string& action, size_t limit = 3);

} // namespace xdebug
