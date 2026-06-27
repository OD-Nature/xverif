#include "api/request_validator.h"
#include "api/response.h"

#include <sstream>

namespace xdebug {

namespace {

std::string join_values(const std::vector<std::string>& values) {
    std::ostringstream os;
    for (size_t i = 0; i < values.size(); ++i) {
        if (i) os << ", ";
        os << values[i];
    }
    return os.str();
}

} // namespace

ValidationResult RequestValidator::validate(const RequestEnvelope& request, const ActionSpec& spec) const {
    ValidationResult result;
    if (request.api_version != kApiVersion) {
        result.ok = false;
        result.code = "UNSUPPORTED_API_VERSION";
        result.message = "expected xdebug.v1";
        return result;
    }
    if (request.action != spec.name) {
        result.ok = false;
        result.code = "UNKNOWN_ACTION";
        result.message = "request action does not match ActionSpec";
        return result;
    }
    for (size_t i = 0; i < spec.args.required.size(); ++i) {
        const std::string& key = spec.args.required[i];
        if (!request.args.contains(key) || request.args[key].is_null()) {
            result.ok = false;
            result.code = "MISSING_FIELD";
            result.message = "args." + key + " is required";
            return result;
        }
    }
    for (std::map<std::string, std::vector<std::string> >::const_iterator it = spec.args.allowed_values.begin();
         it != spec.args.allowed_values.end(); ++it) {
        const std::string& key = it->first;
        if (!request.args.contains(key) || request.args[key].is_null()) continue;
        if (!request.args[key].is_string()) {
            result.ok = false;
            result.code = "INVALID_ARGUMENT";
            result.message = "args." + key + " must be one of: " + join_values(it->second);
            return result;
        }
        std::string value = request.args[key].get<std::string>();
        bool matched = false;
        for (size_t i = 0; i < it->second.size(); ++i) {
            if (value == it->second[i]) {
                matched = true;
                break;
            }
        }
        if (!matched) {
            result.ok = false;
            result.code = "INVALID_ARGUMENT";
            result.message = "args." + key + " must be one of: " + join_values(it->second);
            return result;
        }
    }
    return result;
}

} // namespace xdebug
