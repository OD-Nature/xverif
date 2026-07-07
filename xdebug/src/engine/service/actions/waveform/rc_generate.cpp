#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"

#include "api/text_response_builder.h"
#include "design/protocol/protocol.h"
#include "waveform/server/fsdb_value_reader.h"
#include "waveform/event/event_manager.h"
#include "waveform/event/event_analyzer.h"
#include "waveform/list/list_manager.h"
#include "waveform/list/signal_list.h"
#include "waveform/export/waveform_exporter.h"
#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/service/action_support.h"
#include "waveform/service/rc_generator.h"
#include "waveform/value/logic_value.h"
#include "core/npi/time_contract.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_L1.h"
#include "npi_hdl.h"

#include <fstream>
#include <memory>
#include <algorithm>
#include <map>
#include <sstream>
#include <vector>

namespace xdebug_design {
namespace {
class RcGenerateHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "rc.generate"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        Json a = r.value("args", Json::object());
        std::string config_path = a.value("config_path", "");
        Json output = a.value("output", Json::object());
        std::string rc_path = output.value("path", "");
        bool allow_invalid = a.value("allow_invalid", false);
        if (config_path.empty() || rc_path.empty())
            return Json({{"error","MISSING_FIELD"},{"message","args.config_path and args.output.path required"}});

        // Read config file
        std::ifstream in(config_path);
        if (!in) return Json({{"error","CONFIG_NOT_FOUND"},{"message",config_path}});
        std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        nlohmann::json doc;
        try { doc = nlohmann::json::parse(content); }
        catch (...) { return Json({{"error","INVALID_JSON"},{"message","failed to parse config file"}}); }

        xdebug_waveform::RcConfig cfg;
        std::string err;
        if (!xdebug_waveform::parse_rc_config_json(doc, cfg, err))
            return Json({{"error","PARSE_FAILED"},{"message",err}});

        // Validate signals exist in FSDB
        if (!allow_invalid) {
            auto refs = xdebug_waveform::collect_rc_signal_refs(cfg);
            for (auto& ref : refs) {
                if (ref.kind != "signal") continue;
                if (!npi_fsdb_sig_by_name(g_fsdb_file, ref.input_path.c_str(), NULL)) {
                    return Json({{"error","SIGNAL_NOT_FOUND"},
                        {"message","signal not in FSDB: " + ref.input_path}});
                }
            }
        }

        std::string rc_text = xdebug_waveform::render_signal_rc(cfg);
        if (!xdebug_waveform::write_text_file_creating_dirs(rc_path, rc_text, err))
            return Json({{"error","WRITE_FAILED"},{"message",err}});

        Json counts = Json::parse(xdebug_waveform::rc_config_counts(cfg).dump());
        Json out;
        out["summary"] = {{"written", true}, {"config_path", config_path},
            {"rc_path", rc_path}, {"valid", true}};
        if (counts.contains("group_count")) out["summary"]["group_count"] = counts["group_count"];
        if (counts.contains("signal_count")) out["summary"]["signal_count"] = counts["signal_count"];
        out["config_path"] = config_path;
        out["rc_path"] = rc_path;
        out["written"] = true;
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_rc_generate_handler() {
    return std::unique_ptr<EngineActionHandler>(new RcGenerateHandler);
}

}  // namespace xdebug_design
