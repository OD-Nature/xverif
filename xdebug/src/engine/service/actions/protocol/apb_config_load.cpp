#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "protocol_action_helpers.h"

#include "waveform/apb/apb_manager.h"
#include "waveform/apb/apb_analyzer.h"
#include "waveform/axi/axi_manager.h"
#include "waveform/axi/axi_analyzer.h"
#include "waveform/axi/axi_exporter.h"
#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/value/logic_value.h"

#include "npi_fsdb.h"

#include <fstream>
#include <memory>
#include <ctime>
#include <sstream>

namespace xdebug_design {
namespace {
class ApbConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return protocol_missing_name_error(action_name(), "apb");

        nlohmann::json cfg_j; std::string err_str;
        if (!load_config_from_args(a, cfg_j, err_str))
            return protocol_invalid_arg_error(action_name(), "args.config",
                                              err_str,
                                              "inline args.config object or readable args.config_path");

        const char* legacy[] = {"clk", "sampling", "clock_edge", "posedge", "sample_offset", nullptr};
        for (int i = 0; legacy[i]; ++i) {
            if (cfg_j.contains(legacy[i])) {
                return protocol_invalid_arg_error(
                    action_name(),
                    std::string("config.") + legacy[i],
                    "legacy clock sampling field is not supported",
                    "use config.clock, config.edge, and config.sample_point",
                    {{"did_you_mean", Json::array({"config.clock", "config.edge", "config.sample_point"})}});
            }
        }
        const char* reqs[] = {"clock","paddr","psel","penable","pready",
                              "pslverr","pwrite","pwdata","prdata",nullptr};
        for (int i = 0; reqs[i]; ++i) {
            if (!cfg_j.contains(reqs[i]) || !cfg_j[reqs[i]].is_string() ||
                cfg_j[reqs[i]].get<std::string>().empty())
                return protocol_invalid_arg_error(
                    action_name(),
                    std::string("config.") + reqs[i],
                    std::string("missing or empty field: ") + reqs[i],
                    "non-empty APB signal path");
        }
        ApbConfig cfg;
        cfg.name = name;
        if (!cfg_j.contains("reset") || !parse_reset_config(cfg_j["reset"], cfg.reset, err_str))
            return protocol_invalid_arg_error(action_name(), "config.reset", err_str,
                                              "reset object with signal and polarity");
        npiFsdbSigHandle reset_handle = npi_fsdb_sig_by_name(g_fsdb_file, cfg.reset.signal.c_str(), nullptr);
        NPI_INT32 reset_width = 0;
        if (!reset_handle || !npi_fsdb_sig_property(npiFsdbSigRangeSize, reset_handle, &reset_width) || reset_width != 1)
            return protocol_invalid_arg_error(action_name(), "config.reset.signal",
                                              "APB reset signal must resolve to one bit",
                                              "one-bit waveform signal path");
        cfg.clock_sample.clock = cfg_j["clock"].get<std::string>();
        if (!parse_clock_edge_kind(cfg_j.value("edge", std::string("negedge")),
                                   cfg.clock_sample.edge,
                                   err_str)) {
            return protocol_invalid_enum_error(
                action_name(), "config.edge", err_str,
                Json::array({"posedge", "negedge", "dual"}));
        }
        if (cfg_j.contains("sample_point")) {
            if (!cfg_j["sample_point"].is_string())
                return protocol_invalid_enum_error(
                    action_name(), "config.sample_point",
                    "config.sample_point must be before or after",
                    Json::array({"before", "after"}));
            cfg.clock_sample.has_sample_point = true;
            if (!parse_clock_sample_point_kind(cfg_j["sample_point"].get<std::string>(),
                                               cfg.clock_sample.sample_point,
                                               err_str))
                return protocol_invalid_enum_error(
                    action_name(), "config.sample_point", err_str,
                    Json::array({"before", "after"}));
        }
        if (cfg.clock_sample.edge == ClockEdgeKind::Negedge &&
            cfg.clock_sample.has_sample_point)
            return protocol_invalid_arg_error(
                action_name(),
                "config.sample_point",
                "config.sample_point is only valid with edge:posedge or edge:dual",
                "omit sample_point for negedge, or set config.edge to posedge/dual");
        cfg.paddr = cfg_j["paddr"].get<std::string>();
        cfg.psel = cfg_j["psel"].get<std::string>();
        cfg.penable = cfg_j["penable"].get<std::string>();
        cfg.pwrite = cfg_j["pwrite"].get<std::string>();
        cfg.pwdata = cfg_j["pwdata"].get<std::string>();
        cfg.prdata = cfg_j["prdata"].get<std::string>();
        cfg.pready = cfg_j["pready"].get<std::string>();
        cfg.pslverr = cfg_j["pslverr"].get<std::string>();

        ApbManager am;
        if (!am.create_apb(g_session_id, cfg))
            return make_handler_error("ACTION_FAILED", "failed to save APB config",
                                      {{"cause_code", "CREATE_FAILED"},
                                       {"correct_example", protocol_action_example(action_name())}});

        Json out;
        out["summary"] = {{"name", name}, {"status", "loaded"}};
        out["config"] = apb_config_json(cfg);
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_apb_config_load_handler() {
    return std::unique_ptr<EngineActionHandler>(new ApbConfigLoadHandler);
}

}  // namespace xdebug_design
