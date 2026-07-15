#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "protocol_action_helpers.h"

#include "waveform/apb/apb_manager.h"
#include "waveform/apb/apb_analyzer.h"
#include "waveform/axi/axi_manager.h"
#include "waveform/axi/axi_analyzer.h"
#include "waveform/axi/axi_exporter.h"
#include "waveform/common/clock_sampling.h"
#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/value/logic_value.h"

#include <fstream>
#include <memory>
#include <ctime>
#include <sstream>
#include <vector>

namespace xdebug_design {
namespace {

struct SignalValidation {
    std::string field;
    std::string requested_path;
    std::string resolved_path;
    int width = 0;
};

bool validate_axi_signals(npiFsdbFileHandle fsdb,
                          const nlohmann::json& cfg_j,
                          const xdebug_waveform::ClockSampleSpec& clock_sample,
                          Json& validation,
                          std::string& error) {
    const char* fields[] = {"clock", "reset",
        "awvalid", "awready", "awaddr", "awid", "awlen", "awsize", "awburst",
        "wvalid", "wready", "wdata", "wstrb", "wlast",
        "bvalid", "bready", "bid", "bresp",
        "arvalid", "arready", "araddr", "arid", "arlen", "arsize", "arburst",
        "rvalid", "rready", "rdata", "rid", "rresp", "rlast", nullptr};
    std::vector<SignalValidation> signals;
    validation = Json::object();
    validation["signals"] = Json::array();
    for (int i = 0; fields[i]; ++i) {
        SignalValidation item;
        item.field = fields[i];
        item.requested_path = std::string(fields[i]) == "reset"
            ? cfg_j["reset"].value("signal", "") : cfg_j[fields[i]].get<std::string>();
        npiFsdbSigHandle handle = npi_fsdb_sig_by_name(fsdb, item.requested_path.c_str(), nullptr);
        if (!handle) {
            validation["signals"].push_back({{"field", item.field},
                                                {"requested_path", item.requested_path},
                                                {"status", "signal_not_found"}});
            error = "AXI signal not found: " + item.requested_path;
            return false;
        }
        NPI_INT32 width = 0;
        if (npi_fsdb_sig_property(npiFsdbSigRangeSize, handle, &width) && width > 0)
            item.width = static_cast<int>(width);
        const NPI_BYTE8* full_name = npi_fsdb_sig_property_str(npiFsdbSigFullName, handle);
        item.resolved_path = full_name ? reinterpret_cast<const char*>(full_name)
                                       : item.requested_path;
        validation["signals"].push_back({{"field", item.field},
                                            {"requested_path", item.requested_path},
                                            {"resolved_path", item.resolved_path},
                                            {"width", item.width},
                                            {"status", "ok"}});
        signals.push_back(item);
    }

    auto width_of = [&](const char* field) -> int {
        for (const auto& signal : signals)
            if (signal.field == field) return signal.width;
        return 0;
    };
    auto require_equal = [&](const char* lhs, const char* rhs) -> bool {
        const int lw = width_of(lhs), rw = width_of(rhs);
        if (lw > 0 && rw > 0 && lw != rw) {
            error = std::string("AXI width mismatch: ") + lhs + "=" +
                    std::to_string(lw) + ", " + rhs + "=" + std::to_string(rw);
            return false;
        }
        return true;
    };
    const char* one_bit[] = {"clock", "reset", "awvalid", "awready", "wvalid",
                             "wready", "wlast", "bvalid", "bready", "arvalid",
                             "arready", "rvalid", "rready", "rlast", nullptr};
    for (int i = 0; one_bit[i]; ++i) {
        const int width = width_of(one_bit[i]);
        if (width > 0 && width != 1) {
            error = std::string("AXI control signal must be 1 bit: ") + one_bit[i] +
                    "=" + std::to_string(width);
            return false;
        }
    }
    if (!require_equal("awid", "bid") || !require_equal("arid", "rid") ||
        !require_equal("wdata", "rdata")) return false;
    const int data_width = width_of("wdata"), strobe_width = width_of("wstrb");
    if (data_width > 0 && strobe_width > 0 && data_width != strobe_width * 8) {
        error = "AXI width mismatch: wdata=" + std::to_string(data_width) +
                ", expected 8*wstrb=" + std::to_string(strobe_width * 8);
        return false;
    }

    npiFsdbTime min_time = 0;
    npiFsdbTime max_time = 0;
    npi_fsdb_min_time(fsdb, &min_time);
    npi_fsdb_max_time(fsdb, &max_time);
    xdebug_waveform::ClockSamplePoint first_edge;
    std::string clock_error;
    if (!xdebug_waveform::find_first_clock_sample(
            fsdb, clock_sample, min_time, max_time, first_edge, clock_error)) {
        error = "no requested AXI clock edge found in FSDB";
        if (!clock_error.empty()) error += ": " + clock_error;
        return false;
    }
    validation["clock"] = {{"status", "ok"},
                            {"edge", xdebug_waveform::clock_edge_kind_text(clock_sample.edge)},
                            {"first_edge", first_edge.sample_time}};
    validation["status"] = "ok";
    return true;
}

class AxiConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return protocol_missing_name_error(action_name(), "axi");

        nlohmann::json cfg_j; std::string err;
        if (!load_config_from_args(a, cfg_j, err))
            return protocol_invalid_arg_error(action_name(), "args.config",
                                              err,
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

        // Validate required AXI fields
        const char* reqs[] = {"clock",
            "awvalid","awready","awaddr","awid","awlen","awsize","awburst",
            "wvalid","wready","wdata","wstrb","wlast",
            "bvalid","bready","bid","bresp",
            "arvalid","arready","araddr","arid","arlen","arsize","arburst",
            "rvalid","rready","rdata","rid","rresp","rlast",nullptr};
        for (int i = 0; reqs[i]; ++i) {
            if (!cfg_j.contains(reqs[i]) || !cfg_j[reqs[i]].is_string() ||
                cfg_j[reqs[i]].get<std::string>().empty())
                return protocol_invalid_arg_error(
                    action_name(),
                    std::string("config.") + reqs[i],
                    std::string("missing or empty field: ") + reqs[i],
                    "non-empty AXI signal path");
        }

        AxiConfig cfg; cfg.name = name;
        if (!cfg_j.contains("reset") || !parse_reset_config(cfg_j["reset"], cfg.reset, err))
            return protocol_invalid_arg_error(action_name(), "config.reset", err,
                                              "reset object with signal and polarity");
        cfg.clock_sample.clock = cfg_j["clock"].get<std::string>();
        if (!parse_clock_edge_kind(cfg_j.value("edge", std::string("negedge")),
                                   cfg.clock_sample.edge,
                                   err)) {
            return protocol_invalid_enum_error(
                action_name(), "config.edge", err,
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
                                               err))
                return protocol_invalid_enum_error(
                    action_name(), "config.sample_point", err,
                    Json::array({"before", "after"}));
        }
        if (cfg.clock_sample.edge == ClockEdgeKind::Negedge &&
            cfg.clock_sample.has_sample_point)
            return protocol_invalid_arg_error(
                action_name(),
                "config.sample_point",
                "config.sample_point is only valid with edge:posedge or edge:dual",
                "omit sample_point for negedge, or set config.edge to posedge/dual");
        cfg.awvalid=cfg_j["awvalid"]; cfg.awready=cfg_j["awready"];
        cfg.awaddr=cfg_j["awaddr"]; cfg.awid=cfg_j["awid"];
        cfg.awlen=cfg_j["awlen"]; cfg.awsize=cfg_j["awsize"]; cfg.awburst=cfg_j["awburst"];
        cfg.wvalid=cfg_j["wvalid"]; cfg.wready=cfg_j["wready"];
        cfg.wdata=cfg_j["wdata"]; cfg.wstrb=cfg_j["wstrb"]; cfg.wlast=cfg_j["wlast"];
        cfg.bvalid=cfg_j["bvalid"]; cfg.bready=cfg_j["bready"];
        cfg.bid=cfg_j["bid"]; cfg.bresp=cfg_j["bresp"];
        cfg.arvalid=cfg_j["arvalid"]; cfg.arready=cfg_j["arready"];
        cfg.araddr=cfg_j["araddr"]; cfg.arid=cfg_j["arid"];
        cfg.arlen=cfg_j["arlen"]; cfg.arsize=cfg_j["arsize"]; cfg.arburst=cfg_j["arburst"];
        cfg.rvalid=cfg_j["rvalid"]; cfg.rready=cfg_j["rready"];
        cfg.rdata=cfg_j["rdata"]; cfg.rid=cfg_j["rid"];
        cfg.rresp=cfg_j["rresp"]; cfg.rlast=cfg_j["rlast"];

        Json validation;
        if (!validate_axi_signals(g_fsdb_file, cfg_j, cfg.clock_sample, validation, err))
            return protocol_invalid_arg_error(
                action_name(), "args.config", err,
                "resolvable AXI signals with compatible widths and at least one requested clock edge",
                {{"validation", validation}});

        AxiManager am;
        if (!am.create_axi(g_session_id, cfg))
            return make_handler_error("ACTION_FAILED", "failed to save AXI config",
                                      {{"cause_code", "CREATE_FAILED"},
                                       {"correct_example", protocol_action_example(action_name())}});

        Json out;
        out["summary"] = {{"name", name}, {"status", "loaded"}};
        out["config"] = axi_config_json(cfg);
        out["validation"] = validation;
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_axi_config_load_handler() {
    return std::unique_ptr<EngineActionHandler>(new AxiConfigLoadHandler);
}

}  // namespace xdebug_design
