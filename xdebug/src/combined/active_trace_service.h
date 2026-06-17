#pragma once

#include "api/json_types.h"
#include "npi_fsdb.h"
#include "json.hpp"

#include <string>

namespace xdebug {

class ActiveTraceService {
public:
    // Original entry point (does its own NPI init/load/fsdb_open).
    Json run(const Json& request, const Json& target) const;

    // Unified-engine entry point: NPI + FSDB already loaded by the engine.
    // Returns ordered_json to avoid nlohmann::json→ordered_json conversion crash.
    nlohmann::ordered_json run_engine(const Json& request,
                                       const std::string& daidir,
                                       const std::string& fsdb_path,
                                       npiFsdbFileHandle fsdb) const;
};

} // namespace xdebug
