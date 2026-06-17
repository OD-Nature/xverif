#pragma once

#include "api/json_types.h"
#include "npi_fsdb.h"

#include <string>

namespace xdebug {

class ActiveTraceService {
public:
    // Original entry point (does its own NPI init/load/fsdb_open).
    Json run(const Json& request, const Json& target) const;

    // Unified-engine entry point: NPI + FSDB already loaded by the engine.
    // daidir and fsdb_path are used for response metadata only.
    Json run_engine(const Json& request,
                    const std::string& daidir,
                    const std::string& fsdb_path,
                    npiFsdbFileHandle fsdb) const;
};

} // namespace xdebug
