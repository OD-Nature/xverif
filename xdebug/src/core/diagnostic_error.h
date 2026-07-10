#pragma once

#include "json.hpp"

#include <string>

namespace xdebug_core {

using DiagnosticJson = nlohmann::ordered_json;

class DiagnosticErrorBuilder {
public:
    DiagnosticErrorBuilder(std::string code, std::string message, std::string layer)
        : error_(DiagnosticJson::object()) {
        error_["code"] = code;
        error_["message"] = message;
        error_["recoverable"] = true;
        error_["error_layer"] = layer;
    }

    static DiagnosticErrorBuilder schema(std::string code, std::string message) {
        return DiagnosticErrorBuilder(code, message, "schema");
    }

    static DiagnosticErrorBuilder handler(std::string code, std::string message) {
        return DiagnosticErrorBuilder(code, message, "handler");
    }

    static DiagnosticErrorBuilder wrapper(std::string code, std::string message) {
        return DiagnosticErrorBuilder(code, message, "wrapper");
    }

    static DiagnosticErrorBuilder session_manager(std::string code, std::string message) {
        return DiagnosticErrorBuilder(code, message, "session_manager");
    }

    static DiagnosticErrorBuilder transport(std::string code, std::string message) {
        return DiagnosticErrorBuilder(code, message, "transport");
    }

    static DiagnosticErrorBuilder internal(std::string code, std::string message) {
        DiagnosticErrorBuilder builder(code, message, "internal");
        builder.recoverable(false);
        return builder;
    }

    DiagnosticErrorBuilder& recoverable(bool value) {
        error_["recoverable"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& invalid_arg(const std::string& value) {
        error_["invalid_arg"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& expected(const std::string& value) {
        error_["expected"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& received(const DiagnosticJson& value) {
        error_["received"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& received_type(const std::string& value) {
        error_["received_type"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& allowed_values(const DiagnosticJson& value) {
        error_["allowed_values"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& did_you_mean(const std::string& value) {
        if (!value.empty() &&
            (!error_.contains("invalid_arg") || error_["invalid_arg"] != value)) {
            error_["did_you_mean"] = value;
        }
        return *this;
    }

    DiagnosticErrorBuilder& schema_path(const std::string& value) {
        if (!value.empty()) error_["schema_path"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& required_any_of(const DiagnosticJson& value) {
        if (!value.is_null()) error_["required_any_of"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& missing_name(const std::string& value) {
        error_["missing_name"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& missing_resource(const std::string& value) {
        error_["missing_resource"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& available_values(const DiagnosticJson& value) {
        error_["available_values"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& next_actions(const DiagnosticJson& value) {
        error_["next_actions"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& example_note(const std::string& value) {
        if (!value.empty()) error_["example_note"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& correct_example(const DiagnosticJson& value) {
        if (!value.is_null()) error_["correct_example"] = value;
        return *this;
    }

    DiagnosticErrorBuilder& cause_code(const std::string& value) {
        if (!value.empty()) error_["cause_code"] = value;
        return *this;
    }

    DiagnosticJson to_json() const { return error_; }

private:
    DiagnosticJson error_;
};

inline DiagnosticJson normalize_diagnostic_error(DiagnosticJson error,
                                                 const std::string& default_layer) {
    if (!error.is_object()) error = DiagnosticJson::object();
    if (!error.contains("code")) error["code"] = "ACTION_FAILED";
    if (!error.contains("message")) error["message"] = "action failed";
    if (!error.contains("error_layer")) error["error_layer"] = default_layer;
    if (!error.contains("recoverable")) error["recoverable"] = true;
    if (error.contains("did_you_mean") && error.contains("invalid_arg") &&
        error["did_you_mean"] == error["invalid_arg"]) {
        error.erase("did_you_mean");
    }
    return error;
}

} // namespace xdebug_core
