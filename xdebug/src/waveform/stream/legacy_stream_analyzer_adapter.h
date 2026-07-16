#pragma once

#include "waveform/stream/stream_analyzer.h"

namespace xdebug_waveform {

// Stable seam for differential tests while the columnar stream implementation
// is introduced. Phase 0 deliberately delegates to the existing analyzer so
// public behavior remains unchanged; later phases keep this path as the oracle.
class LegacyStreamAnalyzerAdapter {
public:
    bool analyze(npiFsdbFileHandle file, const StreamConfig& config,
                 const StreamQueryOptions& options, StreamAnalysis& analysis,
                 std::string& error);

private:
    StreamAnalyzer analyzer_;
};

bool analyze_stream_with_legacy_differential(
    npiFsdbFileHandle file, const StreamConfig& config,
    const StreamQueryOptions& options, StreamAnalysis& analysis,
    std::string& error);
bool analyze_stream_cached_with_legacy_differential(
    StreamAnalyzer& analyzer, npiFsdbFileHandle file,
    const StreamConfig& config, const StreamQueryOptions& options,
    AnalysisCacheScope cache_scope, StreamAnalysis& analysis,
    std::string& error);

}  // namespace xdebug_waveform
