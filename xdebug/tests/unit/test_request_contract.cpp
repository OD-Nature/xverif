#include "api/action_registry_init.h"
#include "api/request_envelope.h"
#include "api/request_validator.h"
#include "api/resource_resolver.h"

#include <cassert>

int main() {
    using namespace xdebug;

    const ActionRegistry& registry = default_action_registry();
    const ActionSpec* value_spec = registry.find_spec("value.at");
    const ActionSpec* trace_spec = registry.find_spec("trace.driver");
    const ActionSpec* active_spec = registry.find_spec("trace.active_driver");
    const ActionSpec* actions_spec = registry.find_spec("actions");
    const ActionSpec* abnormal_spec = registry.find_spec("detect_abnormal");
    assert(value_spec && trace_spec && active_spec && actions_spec && abnormal_spec);
    Json value_descriptor = action_spec_descriptor(*value_spec);
    assert(value_descriptor["required_args"].size() == 3);
    assert(value_descriptor["required_args"][2] == "clock");
    assert(value_descriptor["allowed_values"]["format"].is_array());

    Json value_json = {
        {"api_version", "xdebug.v1"},
        {"request_id", "r0"},
        {"action", "value.at"},
        {"target", {{"fsdb", "waves.fsdb"}}},
        {"args", {{"signal", "top.clk"}, {"clock", "top.clk"}, {"time", "10ns"}}},
        {"limits", {{"timeout_ms", 1000}}}
    };
    RequestEnvelope value = RequestEnvelope::from_json(value_json);
    assert(value.api_version == "xdebug.v1");
    assert(value.request_id == "r0");
    assert(value.action == "value.at");
    assert(value.args["signal"] == "top.clk");

    RequestValidator validator;
    ValidationResult validation = validator.validate(value, *value_spec);
    assert(validation.ok);

    Json missing_time_json = value_json;
    missing_time_json["args"].erase("time");
    RequestEnvelope missing_time = RequestEnvelope::from_json(missing_time_json);
    validation = validator.validate(missing_time, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "INVALID_REQUEST");
    assert(validation.data["invalid_arg"] == "args.time");

    Json wrong_version_json = value_json;
    wrong_version_json["api_version"] = "xdebug.v0";
    RequestEnvelope wrong_version = RequestEnvelope::from_json(wrong_version_json);
    validation = validator.validate(wrong_version, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "UNSUPPORTED_API_VERSION");

    Json bad_format_json = value_json;
    bad_format_json["args"]["format"] = 7;
    RequestEnvelope bad_format = RequestEnvelope::from_json(bad_format_json);
    validation = validator.validate(bad_format, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "INVALID_REQUEST");
    assert(validation.data["invalid_arg"] == "args.format");

    Json unknown_top_json = value_json;
    unknown_top_json["unexpected"] = true;
    RequestEnvelope unknown_top = RequestEnvelope::from_json(unknown_top_json);
    validation = validator.validate(unknown_top, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "INVALID_REQUEST");
    assert(validation.data["invalid_arg"] == "unexpected");

    Json top_output_json = value_json;
    top_output_json["output"] = {{"format", "json"}};
    RequestEnvelope top_output = RequestEnvelope::from_json(top_output_json);
    validation = validator.validate(top_output, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "INVALID_REQUEST");
    assert(validation.data["invalid_arg"] == "output");

    Json unknown_arg_json = value_json;
    unknown_arg_json["args"]["unexpected"] = true;
    RequestEnvelope unknown_arg = RequestEnvelope::from_json(unknown_arg_json);
    validation = validator.validate(unknown_arg, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "INVALID_REQUEST");
    assert(validation.data["invalid_arg"] == "args.unexpected");

    Json bad_abnormal_checks_json = {
        {"api_version", "xdebug.v1"},
        {"request_id", "r1"},
        {"action", "detect_abnormal"},
        {"target", {{"fsdb", "waves.fsdb"}}},
        {"args", {
            {"signals", Json::array({"top.sig"})},
            {"checks", Json::array({"unknown_xz"})}
        }}
    };
    RequestEnvelope bad_abnormal_checks = RequestEnvelope::from_json(bad_abnormal_checks_json);
    validation = validator.validate(bad_abnormal_checks, *abnormal_spec);
    assert(!validation.ok);
    assert(validation.code == "INVALID_REQUEST");
    assert(validation.data["invalid_arg"] == "args.checks[0]");
    assert(validation.data["expected"].get<std::string>().find("object") != std::string::npos);

    Json missing_abnormal_check_type_json = bad_abnormal_checks_json;
    missing_abnormal_check_type_json["args"]["checks"] = Json::array({Json::object()});
    RequestEnvelope missing_abnormal_check_type =
        RequestEnvelope::from_json(missing_abnormal_check_type_json);
    validation = validator.validate(missing_abnormal_check_type, *abnormal_spec);
    assert(!validation.ok);
    assert(validation.code == "INVALID_REQUEST");
    assert(validation.data["invalid_arg"] == "args.checks[0].type");
    assert(validation.data["received_type"] == "missing");

    Json wrong_action_json = value_json;
    wrong_action_json["action"] = "trace.driver";
    RequestEnvelope wrong_action = RequestEnvelope::from_json(wrong_action_json);
    validation = validator.validate(wrong_action, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "UNKNOWN_ACTION");

    ResourceResolver resolver;
    ResourceResolution resource = resolver.resolve(value, *value_spec);
    assert(resource.ok && resource.context.waveform);

    RequestEnvelope no_target = value;
    no_target.target = Json::object();
    resource = resolver.resolve(no_target, *value_spec);
    assert(!resource.ok && resource.code == "RESOURCE_REQUIRED");

    RequestEnvelope design = value;
    design.action = "trace.driver";
    design.target = {{"daidir", "simv.daidir"}};
    resource = resolver.resolve(design, *trace_spec);
    assert(resource.ok && resource.context.design);

    RequestEnvelope combined = value;
    combined.action = "trace.active_driver";
    combined.target = {
        {"daidir", "simv.daidir"},
        {"fsdb", "waves.fsdb"}
    };
    resource = resolver.resolve(combined, *active_spec);
    assert(resource.ok && resource.context.design && resource.context.waveform);

    RequestEnvelope active_design_only = combined;
    active_design_only.target = {{"daidir", "simv.daidir"}};
    resource = resolver.resolve(active_design_only, *active_spec);
    assert(!resource.ok && resource.code == "RESOURCE_REQUIRED");

    RequestEnvelope active_waveform_only = combined;
    active_waveform_only.target = {{"fsdb", "waves.fsdb"}};
    resource = resolver.resolve(active_waveform_only, *active_spec);
    assert(!resource.ok && resource.code == "RESOURCE_REQUIRED");

    RequestEnvelope session = value;
    session.target = {{"session_id", "case_a"}};
    resource = resolver.resolve(session, *value_spec);
    assert(resource.ok && resource.context.session);

    RequestEnvelope no_resource;
    no_resource.api_version = "xdebug.v1";
    no_resource.action = "actions";
    resource = resolver.resolve(no_resource, *actions_spec);
    assert(resource.ok);

    return 0;
}
