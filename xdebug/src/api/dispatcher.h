#pragma once

#include "api/json_types.h"
#include "api/action_spec.h"
#include "backend/engine_adapter.h"
#include "session/session_store.h"

#include <string>

namespace xdebug {

class Dispatcher {
public:
    explicit Dispatcher(const std::string& executable_dir);
    Json dispatch(const Json& request);

private:
    Json dispatch_impl(const Json& request);
    Json handle_session(const Json& request, const std::string& action);
    Json handle_batch(const Json& request);
    Json forward_action(const Json& request);
    Json handle_engine_forward(const Json& request, const ActionSpec& spec);
    Json resource_error(const Json& request, const ActionSpec& spec, const Json& target) const;
    Json resolve_target(const Json& request) const;
    std::string mode_for_target(const Json& target) const;

    EngineAdapter adapter_;
    SessionStore sessions_;
};

} // namespace xdebug
