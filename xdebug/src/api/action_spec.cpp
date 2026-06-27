#include "api/action_spec.h"

namespace xdebug {

std::string to_string(ActionStatus status) {
    switch (status) {
    case ActionStatus::Experimental: return "experimental";
    case ActionStatus::Stable: return "stable";
    case ActionStatus::Deprecated: return "deprecated";
    case ActionStatus::Removed: return "removed";
    }
    return "experimental";
}

std::string to_string(ResourceRequirement resource) {
    switch (resource) {
    case ResourceRequirement::None: return "none";
    case ResourceRequirement::Design: return "design";
    case ResourceRequirement::Waveform: return "waveform";
    case ResourceRequirement::Combined: return "combined";
    case ResourceRequirement::Any: return "any";
    case ResourceRequirement::Session: return "session";
    }
    return "none";
}

ActionStatus action_status_from_string(const std::string& value) {
    if (value == "stable") return ActionStatus::Stable;
    if (value == "deprecated") return ActionStatus::Deprecated;
    if (value == "removed") return ActionStatus::Removed;
    return ActionStatus::Experimental;
}

ResourceRequirement resource_requirement_from_string(const std::string& value) {
    if (value == "design") return ResourceRequirement::Design;
    if (value == "waveform") return ResourceRequirement::Waveform;
    if (value == "combined") return ResourceRequirement::Combined;
    if (value == "any") return ResourceRequirement::Any;
    if (value == "session") return ResourceRequirement::Session;
    return ResourceRequirement::None;
}

Json action_spec_descriptor(const ActionSpec& spec) {
    Json descriptor = {
        {"name", spec.name},
        {"category", spec.category},
        {"status", to_string(spec.status)},
        {"requires", to_string(spec.resource)}
    };
    if (!spec.request_schema.empty()) descriptor["request_schema"] = spec.request_schema;
    if (!spec.response_schema.empty()) descriptor["response_schema"] = spec.response_schema;
    if (!spec.handler_kind.empty()) descriptor["handler_kind"] = spec.handler_kind;
    if (!spec.request_examples.empty()) descriptor["request_examples"] = spec.request_examples;
    if (!spec.response_examples.empty()) descriptor["response_examples"] = spec.response_examples;
    if (!spec.args.required.empty()) descriptor["required_args"] = spec.args.required;
    if (!spec.args.allowed_values.empty()) {
        Json allowed = Json::object();
        for (std::map<std::string, std::vector<std::string> >::const_iterator it = spec.args.allowed_values.begin();
             it != spec.args.allowed_values.end(); ++it) {
            allowed[it->first] = it->second;
        }
        descriptor["allowed_values"] = allowed;
    }
    if (spec.name == "signal.changes") {
        descriptor["use_for"] = Json::array({"List exact value-change times", "Inspect waveform timeline edges", "Find first/last raw value changes"});
        descriptor["do_not_use_for"] = Json::array({"Counting clock-sampled high cycles", "Measuring valid active cycles", "Comparing pulse width"});
        descriptor["preferred_alternative"] = {
            {"for_high_cycles", "signal.statistics"},
            {"for_window_boolean_proof", "window.verify"},
            {"for_first_occurrence", "event.find"}
        };
    } else if (spec.name == "signal.statistics") {
        descriptor["use_for"] = Json::array({"Count clock-sampled high/low cycles", "Measure active valid cycles", "Compare signal activity across windows"});
        descriptor["do_not_use_for"] = Json::array({"Listing every value-change timestamp"});
        descriptor["preferred_alternative"] = {{"for_timeline_edges", "signal.changes"}, {"for_counter_min_max_average", "counter.statistics"}};
    } else if (spec.name == "counter.statistics") {
        descriptor["use_for"] = Json::array({"Measure counter min/max/average under valid", "Count max/min occurrences in a clocked window", "Handle up to 64-bit sampled counters"});
        descriptor["do_not_use_for"] = Json::array({"Design-side counter rule explanation"});
        descriptor["preferred_alternative"] = {{"for_design_semantics", "counter.explain"}};
    } else if (spec.name == "window.verify") {
        descriptor["use_for"] = Json::array({"Prove signal conditions across a sampled time window", "Check whether a signal stays 0 or 1"});
    } else if (spec.name == "event.find") {
        descriptor["use_for"] = Json::array({"Find first or next occurrence of a condition/event"});
    }
    return descriptor;
}

} // namespace xdebug
