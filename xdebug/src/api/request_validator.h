#pragma once

#include "api/action_spec.h"
#include "api/request_envelope.h"
#include "core/schema/runtime_schema_validator.h"

#include <string>

namespace xdebug {

struct ValidationResult {
    bool ok = true;
    std::string code;
    std::string message;
    // Single canonical diagnostic object consumed by the dispatcher.
    Json error = Json::object();
};

class RequestValidator {
public:
    ValidationResult validate(const RequestEnvelope& request, const ActionSpec& spec) const;
};

} // namespace xdebug
