#include "api/action_registry_init.h"

namespace xdebug {

namespace {

ActionSpec make_spec(const std::string& name,
                     const std::string& category,
                     ActionStatus status,
                     ResourceRequirement resource,
                     const std::string& handler_kind) {
    ActionSpec spec;
    spec.name = name;
    spec.category = category;
    spec.status = status;
    spec.resource = resource;
    spec.handler_kind = handler_kind;
    return spec;
}

ActionSpec stable_spec(const std::string& name,
                       const std::string& category,
                       ResourceRequirement resource,
                       const std::string& handler_kind) {
    return make_spec(name, category, ActionStatus::Stable, resource, handler_kind);
}

void add_schema_refs(ActionSpec& spec) {
    spec.request_schema = "schemas/v1/actions/" + spec.name + ".request.schema.json";
    spec.response_schema = "schemas/v1/actions/" + spec.name + ".response.schema.json";
    spec.request_examples.push_back("examples/requests/" + spec.name + ".basic.json");
    spec.response_examples.push_back("examples/responses/" + spec.name + ".basic.json");
}

void register_spec(ActionRegistry& r, ActionSpec spec) {
    if (spec.status != ActionStatus::Removed) {
        add_schema_refs(spec);
    }
    r.register_spec(spec);
}

void register_builtin(ActionRegistry& r) {
    ActionSpec actions = stable_spec("actions", "builtin", ResourceRequirement::None, "actions");
    register_spec(r, actions);

    ActionSpec schema = stable_spec("schema", "builtin", ResourceRequirement::None, "schema");
    register_spec(r, schema);

    register_spec(r, stable_spec("batch", "builtin", ResourceRequirement::None, "batch"));
}

void register_session(ActionRegistry& r) {
    register_spec(r, stable_spec("session.open", "session", ResourceRequirement::Any, "session"));
    register_spec(r, stable_spec("session.ensure", "session", ResourceRequirement::Any, "session"));
    register_spec(r, stable_spec("session.list", "session", ResourceRequirement::Session, "session"));
    register_spec(r, stable_spec("session.doctor", "session", ResourceRequirement::Session, "session"));
    register_spec(r, stable_spec("session.kill", "session", ResourceRequirement::Session, "session"));
    register_spec(r, stable_spec("session.close", "session", ResourceRequirement::Session, "session"));
    register_spec(r, stable_spec("session.gc", "session", ResourceRequirement::None, "session"));
}

void register_design(ActionRegistry& r) {
    const char* names[] = {
        "trace.driver", "trace.load", "trace.query",
        "signal.resolve", "signal.canonicalize",
        "trace.expand", "trace.graph", "trace.path", "trace.explain",
        "control.explain", "source.context", "expr.normalize",
        "procedural.assignment", "sequential.update", "fsm.explain",
        "counter.explain", "port.trace", "instance.map", "interface.resolve"
    };
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        ResourceRequirement resource = ResourceRequirement::Design;
        if (std::string(names[i]) == "source.context" || std::string(names[i]) == "expr.normalize") {
            resource = ResourceRequirement::None;
        }
        ActionSpec spec = stable_spec(names[i], "design", resource, "engine_forward");
        if (spec.name == "trace.driver") {
            spec.args.required.push_back("signal");
        }
        register_spec(r, spec);
    }
}

void register_waveform(ActionRegistry& r) {
    struct Entry {
        const char* name;
        ActionStatus status;
    };
    const Entry entries[] = {
        {"cursor.set", ActionStatus::Stable},
        {"cursor.get", ActionStatus::Stable},
        {"cursor.list", ActionStatus::Stable},
        {"cursor.delete", ActionStatus::Stable},
        {"cursor.use", ActionStatus::Stable},
        {"scope.list", ActionStatus::Stable},
        {"rc.generate", ActionStatus::Stable},
        {"value.at", ActionStatus::Stable},
        {"value.batch_at", ActionStatus::Stable},
        {"list.create", ActionStatus::Stable},
        {"list.add", ActionStatus::Stable},
        {"list.delete", ActionStatus::Stable},
        {"list.show", ActionStatus::Stable},
        {"list.value_at", ActionStatus::Stable},
        {"list.validate", ActionStatus::Stable},
        {"list.diff", ActionStatus::Stable},
        {"apb.config.load", ActionStatus::Stable},
        {"apb.config.list", ActionStatus::Stable},
        {"apb.query", ActionStatus::Stable},
        {"apb.cursor", ActionStatus::Stable},
        {"axi.config.load", ActionStatus::Stable},
        {"axi.config.list", ActionStatus::Stable},
        {"axi.query", ActionStatus::Stable},
        {"axi.cursor", ActionStatus::Stable},
        {"axi.analysis", ActionStatus::Stable},
        {"event.config.load", ActionStatus::Stable},
        {"event.config.list", ActionStatus::Stable},
        {"event.find", ActionStatus::Stable},
        {"event.export", ActionStatus::Stable},
        {"verify.conditions", ActionStatus::Stable},
        {"expr.eval_at", ActionStatus::Stable},
        {"window.verify", ActionStatus::Stable},
        {"signal.changes", ActionStatus::Stable},
        {"signal.stability", ActionStatus::Stable},
        {"signal.trend", ActionStatus::Stable},
        {"signal.statistics", ActionStatus::Stable},
        {"sampled_pulse.inspect", ActionStatus::Experimental},
        {"inspect_signal", ActionStatus::Deprecated},
        {"detect_anomaly", ActionStatus::Stable},
        {"handshake.inspect", ActionStatus::Stable},
        {"axi.channel_stall", ActionStatus::Experimental},
        {"axi.outstanding_timeline", ActionStatus::Experimental},
        {"axi.request_response_pair", ActionStatus::Experimental},
        {"axi.latency_outlier", ActionStatus::Experimental},
        {"apb.transfer_window", ActionStatus::Experimental}
    };
    for (size_t i = 0; i < sizeof(entries) / sizeof(entries[0]); ++i) {
        ActionSpec spec = make_spec(entries[i].name, "waveform", entries[i].status,
                                    ResourceRequirement::Waveform, "engine_forward");
        if (spec.name == "value.at") {
            spec.args.required.push_back("signal");
            spec.args.required.push_back("time");
        } else if (spec.name == "rc.generate") {
            spec.args.required.push_back("config_path");
            spec.args.required.push_back("rc_path");
        }
        register_spec(r, spec);
    }
}

void register_combined(ActionRegistry& r) {
    ActionSpec active = stable_spec("trace.active_driver", "combined", ResourceRequirement::Any, "engine_forward");
    active.args.required.push_back("signal");
    active.args.required.push_back("requested_time");
    active.response_examples.push_back("examples/responses/trace.active_driver.exact_assignment.json");
    active.response_examples.push_back("examples/responses/trace.active_driver.control_only.json");
    register_spec(r, active);

    ActionSpec chain = stable_spec("trace.active_driver_chain", "combined",
                                    ResourceRequirement::Any, "engine_forward");
    chain.args.required.push_back("signal");
    chain.args.required.push_back("requested_time");
    register_spec(r, chain);
}

void register_removed(ActionRegistry& r) {
    r.register_spec(make_spec("signal.search", "design", ActionStatus::Removed,
                              ResourceRequirement::Design, "removed"));
}

ActionRegistry* build_registry() {
    ActionRegistry* registry = new ActionRegistry();
    register_builtin(*registry);
    register_session(*registry);
    register_design(*registry);
    register_waveform(*registry);
    register_combined(*registry);
    register_removed(*registry);
    return registry;
}

} // namespace

const ActionRegistry& default_action_registry() {
    static ActionRegistry* registry = build_registry();
    return *registry;
}

} // namespace xdebug
