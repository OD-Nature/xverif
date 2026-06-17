#pragma once

#include "api/json_types.h"

#include <string>

namespace xdebug {

class EngineAdapter {
public:
    explicit EngineAdapter(const std::string& executable_dir);

    // Invoke the unified xdebug-engine subprocess.
    bool invoke(const Json& xdebug_request,
                Json& response,
                std::string& error) const;

private:
    std::string engine_path() const;
    std::string engine_workdir() const;
    std::string executable_dir_;
};

} // namespace xdebug
