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
    assert(value_spec && trace_spec && active_spec && actions_spec);
    Json value_descriptor = action_spec_descriptor(*value_spec);
    assert(value_descriptor["required_args"].size() == 2);
    assert(value_descriptor["allowed_values"]["format"].is_array());

    Json value_json = {
        {"api_version", "xdebug.v1"},
        {"request_id", "r0"},
        {"action", "value.at"},
        {"target", {{"fsdb", "waves.fsdb"}}},
        {"args", {{"signal", "top.clk"}, {"time", "10ns"}}},
        {"limits", {{"timeout_ms", 1000}}},
        {"output", {{"format", "json"}}}
    };
    RequestEnvelope value = RequestEnvelope::from_json(value_json);
    assert(value.api_version == "xdebug.v1");
    assert(value.request_id == "r0");
    assert(value.action == "value.at");
    assert(value.args["signal"] == "top.clk");

    RequestValidator validator;
    ValidationResult validation = validator.validate(value, *value_spec);
    assert(validation.ok);

    RequestEnvelope missing_time = value;
    missing_time.args.erase("time");
    validation = validator.validate(missing_time, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "MISSING_FIELD");

    RequestEnvelope wrong_version = value;
    wrong_version.api_version = "xdebug.v0";
    validation = validator.validate(wrong_version, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "UNSUPPORTED_API_VERSION");

    RequestEnvelope bad_format = value;
    bad_format.args["format"] = "octal";
    validation = validator.validate(bad_format, *value_spec);
    assert(!validation.ok);
    assert(validation.code == "INVALID_ARGUMENT");

    RequestEnvelope wrong_action = value;
    wrong_action.action = "trace.driver";
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
