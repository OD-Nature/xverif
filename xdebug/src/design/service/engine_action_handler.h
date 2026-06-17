#pragma once

#include "json.hpp"

namespace xdebug_design {

using Json = nlohmann::ordered_json;

// Unified action handler interface.
// Follows the same pattern as xdebug_waveform::WaveformActionHandler but:
//  - run() returns Json directly (no stdout printing)
//  - each handler declares its resource requirements
//
// Adding a new action = subclass + one registry line.
// No routing code needs to change.

class EngineActionHandler {
public:
    virtual ~EngineActionHandler() = default;

    // Action name this handler serves (e.g. "trace.driver", "value.at").
    virtual const char* action_name() const = 0;

    // Whether this action requires a loaded design (-dbdir).
    virtual bool needs_design() const = 0;

    // Whether this action requires a loaded waveform (-fsdb).
    virtual bool needs_waveform() const = 0;

    // Execute the action.  Receives the full internal JSON request
    // {api_version, action, target, args, limits, output} and returns
    // the data payload (the value that goes into the "data" field of
    // the response envelope).
    //
    // On error, return {"error": "<code>", "message": "<description>"}.
    virtual Json run(const Json& request) const = 0;
};

} // namespace xdebug_design
