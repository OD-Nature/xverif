#include "engine_action_registry.h"
#include "engine_globals.h"

#include "../../combined/active_trace_service.h"
#include "../../combined/active_trace_chain.h"
#include "../../api/text_response_builder.h"

#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace xdebug_design {

// Registration functions from per-category handler files.
void register_waveform_handlers(EngineActionRegistry& r);
void register_protocol_handlers(EngineActionRegistry& r);
void register_design_handlers(EngineActionRegistry& r);
void register_stream_handlers(EngineActionRegistry& r);

// ═══════════════════════════════════════════════════════════════════════
// Combined action handlers: engine-owned action entries backed by helper payload builders.
// ═══════════════════════════════════════════════════════════════════════

namespace {

std::string scalar_text(const Json& object, const char* key) {
    if (!object.is_object() || !object.contains(key)) return std::string();
    const Json& value = object[key];
    if (!xdebug::is_xout_scalar_json(value)) return std::string();
    return xdebug::json_to_xout_value(value);
}

std::string file_line_text(const Json& object) {
    std::string file = scalar_text(object, "file");
    std::string line = scalar_text(object, "line");
    if (file.empty()) return line;
    if (line.empty() || line == "0") return file;
    return file + ":" + line;
}

class ActiveDriverHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.active_driver"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        return xdebug::build_active_driver_payload(request, g_daidir_path, g_fsdb_path, g_fsdb_file);
    }

    std::string render_xout(const Json& response) const override {
        std::string text = EngineActionHandler::render_xout(response);
        const Json data = response.value("data", Json::object());
        const Json root = data.value("root_driver", Json());
        if (!root.is_object() || root.empty()) return text;

        std::string cause = scalar_text(root, "kind");
        std::string signal = scalar_text(root, "signal");
        std::string location = file_line_text(root);
        if (!signal.empty()) cause += cause.empty() ? signal : " " + signal;
        if (!location.empty()) cause += cause.empty() ? location : " @ " + location;
        if (cause.empty()) return text;

        if (!text.empty() && text.back() != '\n') text.push_back('\n');
        text += "root_cause:\n  " + cause + "\n";
        return text;
    }
};

class ActiveDriverChainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.active_driver_chain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        return xdebug::build_active_driver_chain_payload(request, g_daidir_path, g_fsdb_path, g_fsdb_file);
    }

    std::string render_xout(const Json& response) const override {
        std::string text = EngineActionHandler::render_xout(response);
        const Json data = response.value("data", Json::object());
        const Json chain_data = data.value("chain", Json::object());
        const Json chain = chain_data.value("chain", Json::array());
        if (!chain.is_array() || chain.empty()) return text;

        std::vector<std::string> signals;
        for (const auto& node : chain) {
            std::string signal = scalar_text(node, "signal");
            if (!signal.empty()) signals.push_back(signal);
        }
        if (signals.empty()) return text;

        std::ostringstream path;
        for (size_t i = 0; i < signals.size(); ++i) {
            if (i) path << " -> ";
            path << signals[i];
        }
        if (!text.empty() && text.back() != '\n') text.push_back('\n');
        text += "chain_path:\n  " + path.str() + "\n";
        return text;
    }
};

} // namespace

// ═══════════════════════════════════════════════════════════════════════
// Registry implementation
// ═══════════════════════════════════════════════════════════════════════

void EngineActionRegistry::add(std::unique_ptr<EngineActionHandler> handler) {
    if (!handler) return;
    handlers_[handler->action_name()] = std::move(handler);
}

const EngineActionHandler* EngineActionRegistry::find(const std::string& action) const {
    auto it = handlers_.find(action);
    return it != handlers_.end() ? it->second.get() : nullptr;
}

const EngineActionRegistry& engine_action_registry() {
    static EngineActionRegistry* reg = []() {
        auto* r = new EngineActionRegistry();

        // ── Design handlers ──
        register_design_handlers(*r);

        // ── Waveform handlers ──
        register_waveform_handlers(*r);

        // ── Protocol handlers ──
        register_protocol_handlers(*r);

        // ── Stream handlers ──
        register_stream_handlers(*r);

        // ── Combined handlers ──
        r->add(std::unique_ptr<EngineActionHandler>(new ActiveDriverHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ActiveDriverChainHandler));

        return r;
    }();
    return *reg;
}

} // namespace xdebug_design
