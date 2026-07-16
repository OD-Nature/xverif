#include "waveform/stream/legacy_stream_analyzer_adapter.h"

#include <cstdlib>

namespace xdebug_waveform {

namespace {

Json analysis_snapshot(const StreamConfig& config,
                       const StreamQueryOptions& options,
                       const StreamAnalysis& analysis) {
    Json transfers = Json::array();
    for (const auto& row : analysis.transfers)
        transfers.push_back(stream_row_json(row));
    Json stalls = Json::array();
    for (const auto& stall : analysis.stalls)
        stalls.push_back(stream_stall_json(stall));
    Json packets = Json::array();
    auto append_packet = [&](const StreamPacket& packet) {
        packets.push_back(stream_packet_json(packet));
    };
    if (options.query_kind.empty()) {
        for (const auto& packet : analysis.packets) append_packet(packet);
    } else if (!options.filter.enabled &&
               options.query_kind == "first_packet") {
        if (!analysis.packets.empty()) append_packet(analysis.packets.front());
    } else if (!options.filter.enabled &&
               options.query_kind == "last_packet") {
        if (!analysis.packets.empty()) append_packet(analysis.packets.back());
    } else if (!options.filter.enabled &&
               options.query_kind == "packet_at") {
        for (const auto& packet : analysis.packets) {
            if (packet.packet_index == options.packet_index) {
                append_packet(packet);
                break;
            }
        }
    } else if (options.query_kind == "packet_window") {
        for (std::size_t i = 0; i < analysis.packets.size() &&
             (options.limit <= 0 || static_cast<int>(i) < options.limit); ++i)
            append_packet(analysis.packets[i]);
    }
    Json out = {
        {"summary", stream_summary_json(config, analysis)},
        {"transfers", transfers},
        {"stalls", stalls},
        {"packets", packets},
        {"matched_transfer_count", analysis.matched_transfer_count},
        {"matched_packet_count", analysis.matched_packet_count},
        {"unresolved_filter_count", analysis.unresolved_filter_count},
        {"has_transfer_evidence", analysis.has_transfer_evidence},
        {"has_matched_packet_evidence",
         analysis.has_matched_packet_evidence},
    };
    if (analysis.has_transfer_evidence) {
        out["first_transfer"] = stream_row_json(analysis.first_transfer);
        out["last_transfer"] = stream_row_json(analysis.last_transfer);
    }
    if (analysis.has_matched_packet_evidence) {
        out["first_matched_packet"] =
            stream_packet_json(analysis.first_matched_packet);
        out["last_matched_packet"] =
            stream_packet_json(analysis.last_matched_packet);
    }
    return out;
}

bool differential_enabled() {
    const char* value = std::getenv("XDEBUG_TEST_STREAM_DIFFERENTIAL");
    return value != nullptr && std::string(value) == "1";
}

bool compare_with_legacy(npiFsdbFileHandle file,
                         const StreamConfig& config,
                         const StreamQueryOptions& options,
                         const StreamAnalysis& analysis,
                         std::string& error) {
    if (!differential_enabled()) return true;
    LegacyStreamAnalyzerAdapter legacy;
    StreamAnalysis expected;
    std::string legacy_error;
    if (!legacy.analyze(file, config, options, expected, legacy_error)) {
        error = "legacy stream differential oracle failed: " + legacy_error;
        return false;
    }
    if (analysis_snapshot(config, options, analysis) !=
        analysis_snapshot(config, options, expected)) {
        error = "stream columnar differential mismatch for " + config.name;
        return false;
    }
    return true;
}

}  // namespace

bool LegacyStreamAnalyzerAdapter::analyze(npiFsdbFileHandle file,
                                          const StreamConfig& config,
                                          const StreamQueryOptions& options,
                                          StreamAnalysis& analysis,
                                          std::string& error) {
    return analyzer_.analyze_legacy(
        file, config, options, analysis, error, false);
}

bool analyze_stream_with_legacy_differential(
    npiFsdbFileHandle file, const StreamConfig& config,
    const StreamQueryOptions& options, StreamAnalysis& analysis,
    std::string& error) {
    StreamAnalyzer analyzer;
    if (!analyzer.analyze(file, config, options, analysis, error))
        return false;
    return compare_with_legacy(file, config, options, analysis, error);
}

bool analyze_stream_cached_with_legacy_differential(
    StreamAnalyzer& analyzer, npiFsdbFileHandle file,
    const StreamConfig& config, const StreamQueryOptions& options,
    AnalysisCacheScope cache_scope, StreamAnalysis& analysis,
    std::string& error) {
    if (!analyzer.analyze_cached(
            file, config, options, cache_scope, analysis, error))
        return false;
    return compare_with_legacy(file, config, options, analysis, error);
}

}  // namespace xdebug_waveform
