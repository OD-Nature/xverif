#pragma once

#include "json.hpp"

#include <string>

namespace xdebug_core {

using OrderedJson = nlohmann::ordered_json;

struct RuntimeSchemaValidationResult {
    bool ok = true;
    std::string code;
    std::string message;
    // Single canonical diagnostic object. Callers only wrap it in their
    // transport envelope; they must not copy fields into summary or data.
    OrderedJson error = OrderedJson::object();
};

class RuntimeSchemaValidator {
public:
    RuntimeSchemaValidationResult validate_request(const std::string& action,
                                                   const OrderedJson& request,
                                                   const std::string& schema_ref = std::string()) const;
};

// Return the checked-in, schema-valid basic request example for an action.
// Handler error enrichment uses this instead of copying a failing request.
OrderedJson valid_request_example(const std::string& action);

}  // namespace xdebug_core
