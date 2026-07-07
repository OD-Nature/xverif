#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"

#include "waveform/apb/apb_manager.h"
#include "waveform/apb/apb_analyzer.h"
#include "waveform/axi/axi_manager.h"
#include "waveform/axi/axi_analyzer.h"
#include "waveform/axi/axi_exporter.h"
#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/value/logic_value.h"

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

class AxiAnalysisHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.analysis"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        AxiConfig cfg; std::string err;
        if (!ensure_axi_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string analysis = a.value("analysis", "latency");
        std::string dir = a.value("direction", "all");
        int filter = (dir == "write") ? 1 : (dir == "read") ? 2 : 0;
        std::string id_str = a.value("id", "");

        Json out;
        if (analysis == "osd" || analysis == "outstanding") {
            AxiStatResult stat;
            if (!g_axi_analyzer.get_outstanding_stats(name, filter,
                    id_str.empty() ? nullptr : id_str.c_str(), stat))
                return Json({{"error","ANALYSIS_FAILED"},{"message","outstanding analysis failed"}});
            out["summary"] = {{"name",name},{"analysis","osd"},{"max",stat.max},
                {"min",stat.min},{"avg",stat.avg},{"samples",(int)stat.samples}};
            out["analysis"] = "osd";
            out["max"] = stat.max; out["min"] = stat.min; out["avg"] = stat.avg;
            out["samples"] = (int)stat.samples;
        } else {
            AxiStatResult stat;
            if (!g_axi_analyzer.get_latency_stats(name, filter,
                    id_str.empty() ? nullptr : id_str.c_str(), stat))
                return Json({{"error","ANALYSIS_FAILED"},{"message","latency analysis failed"}});
            out["summary"] = {{"name",name},{"analysis","latency"},{"max",stat.max},
                {"min",stat.min},{"avg",stat.avg},{"samples",(int)stat.samples}};
            out["analysis"] = "latency";
            out["max"] = stat.max; out["min"] = stat.min; out["avg"] = stat.avg;
            out["samples"] = (int)stat.samples;
        }
        out["name"] = name;
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_axi_analysis_handler() {
    return std::unique_ptr<EngineActionHandler>(new AxiAnalysisHandler);
}

}  // namespace xdebug_design
