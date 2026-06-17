#pragma once

#include "api/json_types.h"
#include "npi_fsdb.h"

namespace xdebug {

class ActiveTraceChainService {
public:
    // Original entry point.
    Json run(const Json& request, const Json& target) const;

    // Unified-engine entry point: NPI + FSDB already loaded by the engine.
    Json run_engine(const Json& request,
                    const std::string& daidir,
                    const std::string& fsdb_path,
                    npiFsdbFileHandle fsdb) const;
};

} // namespace xdebug
