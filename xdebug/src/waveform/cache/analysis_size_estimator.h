#pragma once

#include <cstddef>

namespace xdebug_waveform {

struct ApbResult;
struct AxiResult;
struct AxiTransaction;
struct StreamAnalysis;
struct StreamBaseAnalysis;

std::size_t estimate_apb_result_bytes(const ApbResult& result);
std::size_t estimate_axi_transaction_bytes(const AxiTransaction& transaction);
std::size_t estimate_axi_result_bytes(const AxiResult& result);
std::size_t estimate_stream_analysis_bytes(const StreamAnalysis& analysis);
std::size_t estimate_stream_base_analysis_bytes(
    const StreamBaseAnalysis& analysis);

}  // namespace xdebug_waveform
