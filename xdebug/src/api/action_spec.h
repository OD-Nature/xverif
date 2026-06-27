#pragma once

#include "api/json_types.h"

#include <map>
#include <string>
#include <vector>

namespace xdebug {

enum class ActionStatus {
    Experimental,
    Stable,
    Deprecated,
    Removed
};

enum class ResourceRequirement {
    None,
    Design,
    Waveform,
    Combined,
    Any,
    Session
};

struct ArgSpec {
    std::vector<std::string> required;
    std::map<std::string, std::vector<std::string> > allowed_values;
};

struct ActionSpec {
    std::string name;
    std::string category;
    ActionStatus status = ActionStatus::Experimental;
    ResourceRequirement resource = ResourceRequirement::None;
    std::string handler_kind;
    ArgSpec args;
    std::string request_schema;
    std::string response_schema;
    std::vector<std::string> request_examples;
    std::vector<std::string> response_examples;
};

std::string to_string(ActionStatus status);
std::string to_string(ResourceRequirement resource);
ActionStatus action_status_from_string(const std::string& value);
ResourceRequirement resource_requirement_from_string(const std::string& value);
Json action_spec_descriptor(const ActionSpec& spec);

} // namespace xdebug
