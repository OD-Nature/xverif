#pragma once

#include "engine_action_handler.h"

#include <memory>
#include <string>
#include <unordered_map>

namespace xdebug_design {

// Map-based action registry — same pattern as WaveformActionRegistry.
// Thread-safe for reads after initialisation (populated once at startup).

class EngineActionRegistry {
public:
    void add(std::unique_ptr<EngineActionHandler> handler);
    const EngineActionHandler* find(const std::string& action) const;

private:
    std::unordered_map<std::string, std::unique_ptr<EngineActionHandler>> handlers_;
};

// Singleton populated in engine_action_registry.cpp.
const EngineActionRegistry& engine_action_registry();

} // namespace xdebug_design
