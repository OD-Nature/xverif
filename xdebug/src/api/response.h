#pragma once

#include "api/json_types.h"
#include "build_info.h"

#include <string>

namespace xdebug {

static const char* const kApiVersion = "xdebug.v1";
static const char* const kToolVersion = "0.1.0";

inline Json tool_metadata() {
    return {{"name", "xdebug"}, {"version", kToolVersion},
            {"build_id", XDEBUG_BUILD_ID},
            {"git_revision", XDEBUG_GIT_REVISION},
            {"schema_revision", XDEBUG_SCHEMA_REVISION}};
}

Json make_response(const Json& request, const std::string& action, bool ok = true);
Json make_error(const Json& request,
                const std::string& action,
                const std::string& code,
                const std::string& message,
                bool recoverable = true);
Json make_error(const Json& request,
                const std::string& action,
                const Json& error);
Json normalize_engine_response(const Json& response);

} // namespace xdebug
