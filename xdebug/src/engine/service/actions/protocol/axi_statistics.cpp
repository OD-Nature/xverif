#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "protocol_action_helpers.h"
#include "protocol_statistics_filter.h"

#include "waveform/axi/axi_analyzer.h"
#include "waveform/axi/axi_manager.h"

#include <memory>

namespace xdebug_design {
namespace {

class AxiStatisticsHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.statistics"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }

    Json run(const Json& request, EngineActionContext&) const override {
        using namespace xdebug_waveform;
        const Json args = request.value("args", Json::object());
        const std::string name = args.value("name", std::string());
        if (name.empty()) return protocol_missing_name_error(action_name(), "axi");

        StatisticsFilter filter;
        StatisticsFilterError filter_error;
        if (!parse_statistics_filter(args, true, filter, filter_error))
            return protocol_invalid_arg_error(
                action_name(), filter_error.invalid_arg, filter_error.message,
                filter_error.expected);

        AxiConfig config;
        std::string analysis_error;
        if (!ensure_axi_analyzed(name, config, analysis_error)) {
            if (analysis_error.rfind("AXI config not found:", 0) == 0)
                return protocol_config_not_found_error(
                    action_name(), "axi", name);
            if (!g_axi_analyzer.last_cache_error().empty())
                return make_analysis_cache_error(
                    g_axi_analyzer.last_cache_error());
            return protocol_analyze_error(action_name(), "axi", name,
                                          analysis_error);
        }

        if (filter.address_mode != StatisticsAddressMode::None &&
            !g_axi_analyzer.ensure_address_index(name))
            return make_analysis_cache_error(
                g_axi_analyzer.last_cache_error());
        if (filter.has_ids && !g_axi_analyzer.ensure_id_index(name))
            return make_analysis_cache_error(
                g_axi_analyzer.last_cache_error());

        const AxiResult* result = g_axi_analyzer.get_result(name);
        if (!result)
            return protocol_analyze_error(action_name(), "axi", name,
                                          "canonical AXI result unavailable");

        size_t matched_read = 0;
        size_t matched_write = 0;
        size_t unresolved = 0;
        for (const AxiTransaction& transaction : result->all) {
            const StatisticsMatch match = match_statistics_transaction(
                filter, {transaction.is_write, transaction.addr, transaction.id});
            if (match == StatisticsMatch::Unresolved) {
                ++unresolved;
            } else if (match == StatisticsMatch::Yes) {
                if (transaction.is_write) ++matched_write;
                else ++matched_read;
            }
        }

        const AxiDiagnostics& diagnostics = result->diagnostics;
        const bool ambiguous = unresolved > 0 || !diagnostics.analysis_complete;
        Json out;
        out["summary"] = {
            {"name", name},
            {"scanned_transaction_count", result->all.size()},
            {"matched_transaction_count", matched_read + matched_write},
            {"matched_read_count", matched_read},
            {"matched_write_count", matched_write},
            {"unresolved_transaction_count", unresolved},
            {"filter_applied", filter.filter_applied},
            {"analysis_complete", diagnostics.analysis_complete},
            {"analysis_quality", ambiguous ? "ambiguous" : "complete"},
            {"full_scan_count", diagnostics.full_scan_count},
        };
        out["filter"] = statistics_filter_json(filter, true);
        out["notes"] = {{"unresolved_transaction_count",
                         statistics_unresolved_note()}};
        return out;
    }

    std::string render_xout(const Json& response) const override {
        return render_statistics_xout(action_name(), response);
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_axi_statistics_handler() {
    return std::unique_ptr<EngineActionHandler>(new AxiStatisticsHandler);
}

}  // namespace xdebug_design
