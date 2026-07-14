#pragma once

#include "stream_config.h"
#include "stream_expr.h"
#include "waveform/filter/value_filter.h"

#include "npi_fsdb.h"

#include <map>
#include <string>
#include <vector>

namespace xdebug_waveform {

struct StreamRow {
    int cycle = 0;
    npiFsdbTime time = 0;
    bool reset = false;
    bool vld = false;
    bool rdy = true;
    bool bp = false;
    bool sop = false;
    bool eop = false;
    bool transfer = false;
    bool stall = false;
    std::string stall_reason;
    int packet_index = -1;
    int beat_index = 0;
    std::map<std::string, StreamValue> fields;
    std::map<std::string, StreamValue> packet_stable_fields;
    StreamValue channel;
    int control_xz_count = 0;
    int data_xz_count = 0;
};

struct StreamBeat {
    int cycle = 0;
    npiFsdbTime time = 0;
    int beat_index = 0;
    std::map<std::string, StreamValue> fields;
};

struct StreamPacketStableMismatch {
    std::string field;
    int cycle = 0;
    npiFsdbTime time = 0;
    StreamValue expected;
    StreamValue actual;
};

struct StreamPacket {
    int packet_index = 0;
    int start_cycle = 0;
    int end_cycle = 0;
    npiFsdbTime start_time = 0;
    npiFsdbTime end_time = 0;
    int beat_count = 0;
    bool partial_begin = false;
    bool partial_end = false;
    StreamValue channel;
    std::map<std::string, StreamValue> packet_stable_fields;
    std::vector<StreamPacketStableMismatch> packet_stable_mismatches;
    std::vector<StreamBeat> beats;
    std::map<std::string, StreamValue> first_fields;
    std::map<std::string, StreamValue> last_fields;
    // Internal unified filter view. Public JSON keeps packet_stable_fields
    // separate from ordinary beat fields.
    std::map<std::string, StreamValue> first_filter_fields;
    std::map<std::string, StreamValue> last_filter_fields;
};

struct StreamStallWindow {
    int start_cycle = 0;
    int end_cycle = 0;
    npiFsdbTime start_time = 0;
    npiFsdbTime end_time = 0;
    int cycles = 0;
    std::string reason;
};

struct StreamAnalysis {
    std::vector<StreamRow> transfers;
    StreamRow first_transfer;
    StreamRow last_transfer;
    bool has_transfer_evidence = false;
    std::vector<StreamStallWindow> stalls;
    std::vector<StreamPacket> packets;
    int clock_edges = 0;
    int vld_cycles = 0;
    int transfer_count = 0;
    int stall_cycles = 0;
    int complete_packet_count = 0;
    int partial_packet_count = 0;
    int control_xz_count = 0;
    int data_xz_count = 0;
    int ready_bp_conflict_count = 0;
    int packet_stable_mismatch_count = 0;
    int matched_transfer_count = 0;
    int matched_packet_count = 0;
    int unresolved_filter_count = 0;
    StreamPacket first_matched_packet;
    StreamPacket last_matched_packet;
    bool has_matched_packet_evidence = false;
    bool truncated = false;
    bool analysis_complete = true;
    npiFsdbTime requested_begin = 0;
    npiFsdbTime requested_end = 0;
    npiFsdbTime scanned_begin = 0;
    npiFsdbTime scanned_end = 0;
    bool has_scanned_samples = false;
};

struct StreamFilter {
    bool enabled = false;
    std::string position;
    std::map<std::string, ValueFilter> fields;
};

struct StreamValidationIssue {
    std::string severity;
    std::string code;
    std::string message;
};

struct StreamQueryOptions {
    npiFsdbTime begin = 0;
    npiFsdbTime end = 0;
    int limit = 32;
    // 0 follows limit, -1 retains all transfer rows for exact post-scan work.
    int retain_limit = 0;
    bool include_fields = true;
    std::string channel_filter;
    StreamFilter filter;
};

class StreamAnalyzer {
public:
    bool validate_static(npiFsdbFileHandle file, const StreamConfig& config,
                         std::vector<StreamValidationIssue>& issues,
                         std::string& error);
    bool analyze(npiFsdbFileHandle file, const StreamConfig& config,
                 const StreamQueryOptions& options, StreamAnalysis& analysis,
                 std::string& error);

private:
    struct Compiled;
    bool compile(npiFsdbFileHandle file, const StreamConfig& config, Compiled& compiled,
                 std::vector<StreamValidationIssue>* issues, std::string& error);
};

Json stream_row_json(const StreamRow& row);
Json stream_stall_json(const StreamStallWindow& stall);
Json stream_packet_json(const StreamPacket& packet);
Json stream_summary_json(const StreamConfig& config, const StreamAnalysis& analysis);
Json stream_static_validation_json(npiFsdbFileHandle file,
                                   const StreamConfig& config);

} // namespace xdebug_waveform
