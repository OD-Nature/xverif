#pragma once

#include "api/json_types.h"

#include <string>

namespace xdebug {

class ErrorBuilder {
public:
    ErrorBuilder(std::string code, std::string message, std::string layer)
        : error_(Json::object()) {
        error_["code"] = code;
        error_["message"] = message;
        error_["recoverable"] = true;
        error_["error_layer"] = layer;
    }

    static ErrorBuilder schema(std::string code, std::string message) {
        return ErrorBuilder(code, message, "schema");
    }

    static ErrorBuilder handler(std::string code, std::string message) {
        return ErrorBuilder(code, message, "handler");
    }

    static ErrorBuilder wrapper(std::string code, std::string message) {
        return ErrorBuilder(code, message, "wrapper");
    }

    static ErrorBuilder transport(std::string code, std::string message) {
        return ErrorBuilder(code, message, "transport");
    }

    static ErrorBuilder internal(std::string code, std::string message) {
        ErrorBuilder builder(code, message, "internal");
        builder.recoverable(false);
        return builder;
    }

    ErrorBuilder& recoverable(bool value) {
        error_["recoverable"] = value;
        return *this;
    }

    ErrorBuilder& invalid_arg(const std::string& value) {
        error_["invalid_arg"] = value;
        return *this;
    }

    ErrorBuilder& expected(const std::string& value) {
        error_["expected"] = value;
        return *this;
    }

    ErrorBuilder& received(const Json& value) {
        error_["received"] = value;
        return *this;
    }

    ErrorBuilder& received_type(const std::string& value) {
        error_["received_type"] = value;
        return *this;
    }

    ErrorBuilder& allowed_values(const Json& value) {
        error_["allowed_values"] = value;
        return *this;
    }

    ErrorBuilder& did_you_mean(const std::string& value) {
        if (!value.empty()) error_["did_you_mean"] = value;
        return *this;
    }

    ErrorBuilder& schema_path(const std::string& value) {
        if (!value.empty()) error_["schema_path"] = value;
        return *this;
    }

    ErrorBuilder& required_any_of(const Json& value) {
        if (!value.is_null()) error_["required_any_of"] = value;
        return *this;
    }

    ErrorBuilder& missing_name(const std::string& value) {
        error_["missing_name"] = value;
        return *this;
    }

    ErrorBuilder& missing_resource(const std::string& value) {
        error_["missing_resource"] = value;
        return *this;
    }

    ErrorBuilder& available_values(const Json& value) {
        error_["available_values"] = value;
        return *this;
    }

    ErrorBuilder& next_actions(const Json& value) {
        error_["next_actions"] = value;
        return *this;
    }

    ErrorBuilder& example_note(const std::string& value) {
        if (!value.empty()) error_["example_note"] = value;
        return *this;
    }

    ErrorBuilder& correct_example(const Json& value) {
        if (!value.is_null()) error_["correct_example"] = value;
        return *this;
    }

    ErrorBuilder& cause_code(const std::string& value) {
        if (!value.empty()) error_["cause_code"] = value;
        return *this;
    }

    Json to_json() const { return error_; }

private:
    Json error_;
};

inline Json ensure_error_layer(Json error, const std::string& layer) {
    if (!error.is_object()) error = Json::object();
    if (!error.contains("error_layer")) error["error_layer"] = layer;
    if (!error.contains("recoverable")) error["recoverable"] = true;
    return error;
}

} // namespace xdebug
