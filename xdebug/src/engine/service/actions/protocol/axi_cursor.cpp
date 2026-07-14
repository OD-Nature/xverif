#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "protocol_action_helpers.h"

#include "waveform/apb/apb_manager.h"
#include "waveform/apb/apb_analyzer.h"
#include "waveform/axi/axi_manager.h"
#include "waveform/axi/axi_analyzer.h"
#include "waveform/axi/axi_exporter.h"
#include "waveform/axi/axi_transaction_json.h"
#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/value/logic_value.h"
#include "core/npi/time_contract.h"

#include <fstream>
#include <memory>
#include <ctime>
#include <sstream>

namespace xdebug_design {
namespace {

static bool ensure_axi_analyzed(const std::string& name,
                                 xdebug_waveform::AxiConfig& cfg,
                                 std::string& err) {
    xdebug_waveform::AxiManager am;
    if (!am.get_axi(xdebug_waveform::g_session_id, name, cfg)) {
        err = "AXI config not found: " + name;
        return false;
    }
    if (!xdebug_waveform::g_axi_analyzer.analyze(name,
            xdebug_waveform::g_fsdb_file, cfg)) {
        err = "Failed to analyze AXI: " + name;
        return false;
    }
    return true;
}

class AxiCursorHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.cursor"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        std::string op = a.value("op", "begin");
        if (name.empty()) return protocol_missing_name_error(action_name(), "axi");

        AxiConfig cfg; std::string err;
        if (!ensure_axi_analyzed(name, cfg, err))
            return err.rfind("AXI config not found:", 0) == 0
                ? protocol_config_not_found_error(action_name(), "axi", name)
                : protocol_analyze_error(action_name(), "axi", name, err);

        std::string dir = a.value("direction", "all");
        int filter = (dir == "write") ? 1 : (dir == "read") ? 2 : 0;

        const AxiTransaction* txn = nullptr;
        bool ok = false;
        if (op == "begin") ok = g_axi_analyzer.cursor_begin(name, filter, txn);
        else if (op == "next") ok = g_axi_analyzer.cursor_next(name, filter, txn);
        else if (op == "prev" || op == "pre") ok = g_axi_analyzer.cursor_prev(name, filter, txn);
        else if (op == "last") ok = g_axi_analyzer.cursor_last(name, filter, txn);
        else return protocol_invalid_enum_error(
            action_name(), "args.op",
            "op must be begin, next, prev, or last",
            Json::array({"begin", "next", "prev", "last"}));

        Json out;
        size_t index = 0;
        size_t total = 0;
        g_axi_analyzer.cursor_state(name, filter, index, total);
        out["summary"] = {{"name",name},{"op",op},{"direction",dir},{"found",ok},
                          {"index", ok ? Json(index) : Json(nullptr)}, {"index_base", 1},
                          {"total_count", total}, {"at_begin", ok && index == 1},
                          {"at_end", ok && index == total}};
        if (ok && txn) {
            out["transaction"] = axi_transaction_to_json(g_fsdb_file, *txn, false);
        }
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_axi_cursor_handler() {
    return std::unique_ptr<EngineActionHandler>(new AxiCursorHandler);
}

}  // namespace xdebug_design
