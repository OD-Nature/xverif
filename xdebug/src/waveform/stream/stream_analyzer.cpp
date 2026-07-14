#include "stream_analyzer.h"

#include "../server/fsdb_scan_utils.h"
#include "../server/fsdb_value_reader.h"
#include "../value/logic_value.h"

#include "npi_fsdb.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <map>
#include <set>

namespace xdebug_waveform {

std::string format_time(npiFsdbTime t);

namespace {

void issue(std::vector<StreamValidationIssue>& issues,
           const std::string& severity,
           const std::string& code,
           const std::string& message) {
    issues.push_back(StreamValidationIssue{severity, code, message});
}

std::vector<std::string> sorted_signals(const std::set<std::string>& signals) {
    return std::vector<std::string>(signals.begin(), signals.end());
}

StreamValue x_value() {
    return StreamValue{"x", false};
}

unsigned long long parse_user_u64(const std::string& text, bool& ok, std::string& error) {
    LogicValue literal = parse_user_logic_literal(text);
    if (!literal.valid) {
        ok = false;
        error = literal.error;
        return 0;
    }
    if (logic_value_has_xz(literal) || literal.bits.size() > 63) {
        ok = false;
        error = "match value must be a known literal up to 63 bits: " + text;
        return 0;
    }
    unsigned long long out = 0;
    for (char c : literal.bits) {
        out <<= 1ULL;
        if (c == '1') out |= 1ULL;
    }
    ok = true;
    return out;
}

bool value_u64(const StreamValue& value, unsigned long long& out) {
    if (!value.known || value.bits.size() > 63) return false;
    out = 0;
    for (char c : value.bits) {
        out <<= 1ULL;
        if (c == '1') out |= 1ULL;
        else if (c != '0') return false;
    }
    return true;
}

bool stream_value_equal(const StreamValue& a, const StreamValue& b) {
    return a.known == b.known && a.bits == b.bits;
}

std::string stream_value_key(const StreamValue& value) {
    return value.bits.empty() ? "<none>" : value.bits;
}

std::string sample_bits_from_raw(std::string text) {
    if (text.size() >= 2 && text[0] == '\'' &&
        (text[1] == 'b' || text[1] == 'B' || text[1] == 'h' || text[1] == 'H' ||
         text[1] == 'd' || text[1] == 'D')) {
        text = text.substr(2);
    }
    std::string bits;
    for (char c : text) {
        if (c == '_' || std::isspace(static_cast<unsigned char>(c))) continue;
        if (c == '0' || c == '1' || c == 'x' || c == 'X' || c == 'z' || c == 'Z') {
            bits.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        }
    }
    return bits.empty() ? "x" : bits;
}

Json fields_json(const std::map<std::string, StreamValue>& fields) {
    Json out = Json::object();
    for (const auto& kv : fields) out[kv.first] = stream_value_json(kv.second);
    return out;
}

Json stable_mismatches_json(const std::vector<StreamStableMismatch>& mismatches) {
    Json arr = Json::array();
    for (const auto& mismatch : mismatches) {
        arr.push_back({{"field", mismatch.field},
                       {"cycle", mismatch.cycle},
                       {"time", format_time(mismatch.time)},
                       {"expected", stream_value_json(mismatch.expected)},
                       {"actual", stream_value_json(mismatch.actual)}});
    }
    return arr;
}

Json beat_json(const StreamBeat& beat) {
    return Json{{"cycle", beat.cycle},
                {"time", format_time(beat.time)},
                {"beat_index", beat.beat_index},
                {"fields", fields_json(beat.fields)}};
}

Json beat_preview_json(const std::vector<StreamBeat>& beats) {
    Json head = Json::array();
    Json tail = Json::array();
    size_t n = beats.size();
    size_t head_count = std::min<size_t>(5, n);
    for (size_t i = 0; i < head_count; ++i) head.push_back(beat_json(beats[i]));
    if (n > 5) {
        size_t tail_start = n > 10 ? n - 5 : 5;
        for (size_t i = tail_start; i < n; ++i) tail.push_back(beat_json(beats[i]));
    }
    return Json{{"total_beats", n},
                {"truncated", n > 10},
                {"head", head},
                {"tail", tail}};
}

} // namespace

struct StreamAnalyzer::Compiled {
    StreamExpression clock;
    StreamExpression reset;
    StreamExpression vld;
    StreamExpression rdy;
    StreamExpression bp;
    StreamExpression sop;
    StreamExpression eop;
    StreamExpression data;
    StreamExpression channel;
    std::map<std::string, StreamExpression> data_fields;
    std::map<std::string, StreamExpression> stable_fields;
    std::map<std::string, StreamExpression> beat_fields;
    std::set<std::string> deps;
    std::map<std::string, std::string> dep_paths;
};

bool StreamAnalyzer::compile(npiFsdbFileHandle file, const StreamConfig& config, Compiled& c,
                             std::vector<StreamValidationIssue>* issues, std::string& error) {
    auto parse_one = [&](const std::string& label, const std::string& text, StreamExpression& expr) -> bool {
        if (text.empty()) return true;
        std::string parse_error;
        if (!expr.parse(text, parse_error)) {
            error = label + " expression parse failed: " + parse_error;
            return false;
        }
        for (const auto& sig : expr.signals()) c.deps.insert(sig);
        return true;
    };

    if (!parse_one("clock", config.clock_sample.clock, c.clock)) return false;
    if (!c.clock.is_plain_signal()) {
        if (issues) issue(*issues, "WARNING", "CLOCK_COMPLEX",
            "clock expression is not a plain signal; edge detection uses expression dependency changes");
    }
    if (!parse_one("reset", config.reset, c.reset)) return false;
    if (!parse_one("vld", config.vld, c.vld)) return false;
    if (!parse_one("rdy", config.rdy, c.rdy)) return false;
    if (!parse_one("bp", config.bp, c.bp)) return false;
    if (!parse_one("sop", config.sop, c.sop)) return false;
    if (!parse_one("eop", config.eop, c.eop)) return false;
    if (!parse_one("data", config.data, c.data)) return false;
    if (!parse_one("channel_id", config.channel_id, c.channel)) return false;
    for (const auto& kv : config.data_fields) {
        StreamExpression expr;
        if (!parse_one("data_fields." + kv.first, kv.second, expr)) return false;
        c.data_fields[kv.first] = std::move(expr);
    }
    for (const auto& kv : config.stable_fields) {
        StreamExpression expr;
        if (!parse_one("stable_fields." + kv.first, kv.second, expr)) return false;
        c.stable_fields[kv.first] = std::move(expr);
    }
    for (const auto& kv : config.beat_fields) {
        StreamExpression expr;
        if (!parse_one("beat_fields." + kv.first, kv.second, expr)) return false;
        c.beat_fields[kv.first] = std::move(expr);
    }

    for (const auto& sig : c.deps) {
        auto alias = config.signals.find(sig);
        if (alias == config.signals.end()) {
            error = "stream " + config.name + " expression references unknown signal alias: " + sig;
            return false;
        }
        c.dep_paths[sig] = alias->second;
        if (!npi_fsdb_sig_by_name(file, alias->second.c_str(), NULL)) {
            error = "signal not found for alias " + sig + ": " + alias->second;
            return false;
        }
    }
    return true;
}

bool StreamAnalyzer::validate_static(npiFsdbFileHandle file, const StreamConfig& config,
                                     std::vector<StreamValidationIssue>& issues,
                                     std::string& error) {
    issues.clear();
    if (!stream_name_valid(config.name)) issue(issues, "ERROR", "INVALID_NAME", "invalid stream name");
    if (config.data.empty() && config.data_fields.empty())
        if (config.beat_fields.empty() && config.stable_fields.empty())
            issue(issues, "ERROR", "MISSING_DATA", "stream requires data, data_fields, stable_fields, or beat_fields");
    if ((config.sop.empty()) != (config.eop.empty()))
        issue(issues, "ERROR", "PACKET_PAIR", "sop/eop must be configured together");
    if ((config.channel_id_valid == "sop" || config.channel_id_valid == "eop") && !stream_packet_enabled(config))
        issue(issues, "ERROR", "CHANNEL_VALID_REQUIRES_PACKET", "channel_id_valid=sop/eop requires sop/eop");
    if ((config.channel_id_valid == "sop" || config.channel_id_valid == "eop") && config.channel_id.empty())
        issue(issues, "ERROR", "CHANNEL_VALID_REQUIRES_CHANNEL", "channel_id_valid=sop/eop requires channel_id");
    if (config.allow_interleaving) {
        if (!stream_packet_enabled(config))
            issue(issues, "ERROR", "INTERLEAVING_REQUIRES_PACKET", "allow_interleaving requires sop/eop");
        if (config.channel_id.empty())
            issue(issues, "ERROR", "INTERLEAVING_REQUIRES_CHANNEL", "allow_interleaving requires channel_id");
        if (config.channel_id_valid != "every_beat")
            issue(issues, "ERROR", "INTERLEAVING_REQUIRES_EVERY_BEAT_CHANNEL", "allow_interleaving requires channel_id_valid=every_beat");
    }

    Compiled compiled;
    if (!compile(file, config, compiled, &issues, error)) {
        issue(issues, "ERROR", "COMPILE_FAILED", error);
        return false;
    }
    return true;
}

bool StreamAnalyzer::analyze(npiFsdbFileHandle file, const StreamConfig& config,
                             const StreamQueryOptions& options, StreamAnalysis& analysis,
                             std::string& error) {
    analysis = StreamAnalysis();
    analysis.requested_begin = options.begin;
    analysis.requested_end = options.end;
    ClockSampleSpec clock_sample = config.clock_sample;
    if (!normalize_clock_sample_spec(file, clock_sample, error)) return false;
    Compiled compiled;
    if (!compile(file, config, compiled, nullptr, error)) return false;
    std::vector<std::string> deps = sorted_signals(compiled.deps);
    std::vector<std::string> clock_deps = sorted_signals(compiled.clock.signals());
    if (clock_deps.empty()) {
        error = "clock expression has no signal dependency";
        return false;
    }
    std::vector<ClockSampleSignal> clock_signals;
    for (const auto& sig_name : clock_deps) {
        auto path_it = compiled.dep_paths.find(sig_name);
        if (path_it == compiled.dep_paths.end()) {
            error = "clock dependency alias missing from stream signals: " + sig_name;
            return false;
        }
        npiFsdbSigHandle sig = npi_fsdb_sig_by_name(file, path_it->second.c_str(), NULL);
        if (!sig) {
            error = "signal not found for alias " + sig_name + ": " + path_it->second;
            return false;
        }
        clock_signals.push_back({sig_name, path_it->second, sig});
    }
    std::vector<ClockSampleSignal> sample_signals;
    for (const auto& sig_name : deps) {
        auto path_it = compiled.dep_paths.find(sig_name);
        if (path_it == compiled.dep_paths.end()) {
            error = "sample dependency alias missing from stream signals: " + sig_name;
            return false;
        }
        npiFsdbSigHandle sig = npi_fsdb_sig_by_name(file, path_it->second.c_str(), NULL);
        if (!sig) {
            error = "signal not found for alias " + sig_name + ": " + path_it->second;
            return false;
        }
        sample_signals.push_back({sig_name, path_it->second, sig});
    }
    std::vector<ClockSample> sampled_edges;
    ClockExpressionSampleScanner scanner(file, clock_sample.edge, clock_sample.sample_point);
    int sample_count = 0;
    bool sample_truncated = false;
    if (!scanner.scan(clock_signals, sample_signals, options.begin, options.end,
        npiFsdbBinStrVal, 'b', -1,
        [&](const std::map<std::string, std::string>& raw_values,
            bool& known,
            bool& one,
            std::string& eval_error) -> bool {
            std::map<std::string, StreamValue> clock_values;
            for (const auto& sig_name : clock_deps) {
                auto it = raw_values.find(sig_name);
                if (it == raw_values.end()) {
                    eval_error = "clock dependency missing: " + sig_name;
                    return false;
                }
                std::string bits = sample_bits_from_raw(it->second);
                clock_values[sig_name] = StreamValue{bits, bits.find_first_of("xz") == std::string::npos};
            }
            StreamValue clock_value;
            std::string expr_error;
            if (!compiled.clock.evaluate(clock_values, clock_value, expr_error)) {
                eval_error = "clock evaluate failed: " + expr_error;
                return false;
            }
            known = clock_value.known;
            one = stream_value_truthy(clock_value, false);
            return true;
        },
        [&](const ClockSample& sample) -> bool {
            sampled_edges.push_back(sample);
            return true;
        }, error, sample_count, sample_truncated)) {
        return false;
    }

    int packet_index = 0;
    StreamStallWindow current_stall;
    bool in_stall = false;
    struct PacketState {
        bool active = false;
        StreamPacket packet;
    };
    PacketState single_packet;
    std::map<std::string, PacketState> channel_packets;

    auto finish_stall = [&](npiFsdbTime end_time, int end_cycle) {
        if (!in_stall) return;
        current_stall.end_time = end_time;
        current_stall.end_cycle = end_cycle;
        analysis.stalls.push_back(current_stall);
        in_stall = false;
    };

    auto finish_packet = [&](PacketState& state, bool partial_end) {
        if (!state.active) return;
        state.packet.partial_end = partial_end;
        analysis.stable_mismatch_count += static_cast<int>(state.packet.stable_mismatches.size());
        analysis.packets.push_back(state.packet);
        analysis.packet_count++;
        state.active = false;
        state.packet = StreamPacket();
    };

    auto start_packet = [&](PacketState& state, const StreamRow& row, bool partial_begin) {
        if (state.active) finish_packet(state, true);
        state.active = true;
        state.packet = StreamPacket();
        state.packet.packet_index = packet_index++;
        state.packet.start_cycle = row.cycle;
        state.packet.end_cycle = row.cycle;
        state.packet.start_time = row.time;
        state.packet.end_time = row.time;
        state.packet.partial_begin = partial_begin;
        state.packet.stable_fields = row.stable_fields;
        if (config.channel_id_valid == "sop" || config.channel_id_valid == "every_beat") {
            state.packet.channel = row.channel;
        }
    };

    auto append_packet_beat = [&](PacketState& state, StreamRow& row) {
        row.packet_index = state.packet.packet_index;
        row.beat_index = state.packet.beat_count;
        state.packet.end_cycle = row.cycle;
        state.packet.end_time = row.time;
        state.packet.beat_count++;
        if (state.packet.first_fields.empty()) state.packet.first_fields = row.fields;
        state.packet.last_fields = row.fields;
        if (config.channel_id_valid == "eop" && row.eop) state.packet.channel = row.channel;
        if (config.channel_id_valid == "every_beat" && state.packet.channel.bits.empty()) {
            state.packet.channel = row.channel;
        }
        for (const auto& kv : row.stable_fields) {
            auto it = state.packet.stable_fields.find(kv.first);
            if (it == state.packet.stable_fields.end()) {
                state.packet.stable_fields[kv.first] = kv.second;
                continue;
            }
            if (!stream_value_equal(it->second, kv.second)) {
                StreamStableMismatch mismatch;
                mismatch.field = kv.first;
                mismatch.cycle = row.cycle;
                mismatch.time = row.time;
                mismatch.expected = it->second;
                mismatch.actual = kv.second;
                state.packet.stable_mismatches.push_back(mismatch);
            }
        }
        StreamBeat beat;
        beat.cycle = row.cycle;
        beat.time = row.time;
        beat.beat_index = row.beat_index;
        beat.fields = row.fields;
        state.packet.beats.push_back(beat);
    };

    int cycle = 0;
    for (const auto& sample : sampled_edges) {
        npiFsdbTime t = sample.time;
        if (!analysis.has_scanned_samples) {
            analysis.scanned_begin = t;
            analysis.has_scanned_samples = true;
        }
        analysis.scanned_end = t;
        analysis.clock_edges++;
        std::map<std::string, StreamValue> values;
        for (size_t i = 0; i < deps.size(); ++i) {
            std::string raw = i < sample.values.size() ? sample.values[i] : "'bx";
            std::string bits = sample_bits_from_raw(raw);
            values[deps[i]] = StreamValue{bits, bits.find_first_of("xz") == std::string::npos};
        }

        auto eval = [&](StreamExpression& expr, const std::string& label) -> StreamValue {
            if (expr.text().empty()) return StreamValue{"0", true};
            StreamValue out;
            std::string eval_error;
            if (!expr.evaluate(values, out, eval_error)) {
                error = label + " evaluate failed: " + eval_error;
                return x_value();
            }
            return out;
        };

        StreamValue reset_v = config.reset.empty() ? StreamValue{"0", true} : eval(compiled.reset, "reset");
        if (!error.empty()) return false;
        StreamValue vld_v = eval(compiled.vld, "vld");
        if (!error.empty()) return false;
        StreamValue rdy_v = config.rdy.empty() ? StreamValue{"1", true} : eval(compiled.rdy, "rdy");
        if (!error.empty()) return false;
        StreamValue bp_v = config.bp.empty() ? StreamValue{"0", true} : eval(compiled.bp, "bp");
        if (!error.empty()) return false;
        StreamValue sop_v = config.sop.empty() ? StreamValue{"0", true} : eval(compiled.sop, "sop");
        if (!error.empty()) return false;
        StreamValue eop_v = config.eop.empty() ? StreamValue{"0", true} : eval(compiled.eop, "eop");
        if (!error.empty()) return false;

        StreamRow row;
        row.cycle = cycle;
        row.time = t;
        row.reset = stream_value_truthy(reset_v, true);
        row.vld = stream_value_truthy(vld_v, false);
        row.rdy = stream_value_truthy(rdy_v, false);
        row.bp = stream_value_truthy(bp_v, true);
        row.sop = stream_value_truthy(sop_v, false);
        row.eop = stream_value_truthy(eop_v, false);
        row.control_xz_count = (stream_value_has_xz(reset_v) ? 1 : 0) +
                               (stream_value_has_xz(vld_v) ? 1 : 0) +
                               (stream_value_has_xz(rdy_v) ? 1 : 0) +
                               (stream_value_has_xz(bp_v) ? 1 : 0) +
                               (stream_value_has_xz(sop_v) ? 1 : 0) +
                               (stream_value_has_xz(eop_v) ? 1 : 0);

        bool flow = true;
        if (!config.rdy.empty()) flow = flow && row.rdy;
        if (!config.bp.empty()) flow = flow && !row.bp;
        row.transfer = row.vld && flow && !row.reset;
        if (!config.rdy.empty() && !config.bp.empty()) {
            row.stall = row.vld && (!row.rdy || row.bp);
            if (!row.rdy && row.bp) row.stall_reason = "rdy_low_and_bp_high";
            else if (!row.rdy) row.stall_reason = "rdy_low";
            else if (row.bp) row.stall_reason = "bp_high";
        } else if (!config.rdy.empty()) {
            row.stall = row.vld && !row.rdy;
            if (row.stall) row.stall_reason = "rdy_low";
        } else if (!config.bp.empty()) {
            row.stall = row.vld && row.bp;
            if (row.stall) row.stall_reason = "bp_high";
        }
        if (row.vld) analysis.vld_cycles++;
        if (row.stall) analysis.stall_cycles++;
        if (row.vld && row.rdy && row.bp && !config.rdy.empty() && !config.bp.empty())
            analysis.ready_bp_conflict_count++;
        analysis.control_xz_count += row.control_xz_count;

        if (!config.data.empty()) {
            row.fields["data"] = eval(compiled.data, "data");
            if (!error.empty()) return false;
        }
        for (auto& kv : compiled.data_fields) {
            row.fields[kv.first] = eval(kv.second, "data_fields." + kv.first);
            if (!error.empty()) return false;
        }
        for (auto& kv : compiled.beat_fields) {
            row.fields[kv.first] = eval(kv.second, "beat_fields." + kv.first);
            if (!error.empty()) return false;
        }
        for (auto& kv : compiled.stable_fields) {
            row.stable_fields[kv.first] = eval(kv.second, "stable_fields." + kv.first);
            if (!error.empty()) return false;
        }
        if (!config.channel_id.empty()) {
            row.channel = eval(compiled.channel, "channel_id");
            if (!error.empty()) return false;
        }
        for (const auto& kv : row.fields) {
            if (stream_value_has_xz(kv.second)) row.data_xz_count++;
        }
        for (const auto& kv : row.stable_fields) {
            if (stream_value_has_xz(kv.second)) row.data_xz_count++;
        }
        analysis.data_xz_count += row.data_xz_count;

        bool channel_ok = options.channel_filter.empty();
        if (!options.channel_filter.empty()) {
            bool ok = false;
            std::string parse_error;
            unsigned long long want = parse_user_u64(options.channel_filter, ok, parse_error);
            if (!ok) {
                error = parse_error.empty() ? "invalid channel filter: " + options.channel_filter : parse_error;
                return false;
            }
            unsigned long long got = 0;
            channel_ok = value_u64(row.channel, got) && got == want;
        }

        if (row.stall) {
            if (!in_stall) {
                in_stall = true;
                current_stall = StreamStallWindow();
                current_stall.start_cycle = cycle;
                current_stall.start_time = t;
                current_stall.reason = row.stall_reason;
            }
            current_stall.cycles++;
        } else {
            finish_stall(t, cycle);
        }

        if (row.transfer) {
            analysis.transfer_count++;
            if (stream_packet_enabled(config)) {
                PacketState* state = &single_packet;
                if (config.allow_interleaving) {
                    if (row.channel.bits.empty() || stream_value_has_xz(row.channel)) {
                        error = "interleaved packet stream requires known channel_id on every transfer";
                        return false;
                    }
                    state = &channel_packets[stream_value_key(row.channel)];
                } else if (config.channel_id_valid == "every_beat" && single_packet.active &&
                           !single_packet.packet.channel.bits.empty() &&
                           !stream_value_equal(single_packet.packet.channel, row.channel)) {
                    error = "non-interleaved packet channel_id changed within a packet";
                    return false;
                }

                if (row.sop) start_packet(*state, row, false);
                else if (!state->active && row.eop) start_packet(*state, row, true);

                if (state->active) {
                    append_packet_beat(*state, row);
                    if (row.eop) finish_packet(*state, false);
                }
            }
            if (channel_ok) {
                if (!analysis.has_transfer_evidence) {
                    analysis.first_transfer = row;
                    analysis.has_transfer_evidence = true;
                }
                analysis.last_transfer = row;
                const int retain_limit = options.retain_limit == 0
                    ? options.limit : options.retain_limit;
                if (retain_limit <= 0 || static_cast<int>(analysis.transfers.size()) < retain_limit)
                    analysis.transfers.push_back(row);
                else
                    analysis.truncated = true;
            }
        }

        cycle++;
    }
    if (sample_truncated) analysis.truncated = true;
    finish_stall(sampled_edges.empty() ? options.end : sampled_edges.back().time, cycle);
    finish_packet(single_packet, true);
    for (auto& kv : channel_packets) finish_packet(kv.second, true);
    std::sort(analysis.packets.begin(), analysis.packets.end(),
              [](const StreamPacket& a, const StreamPacket& b) {
                  if (a.start_time != b.start_time) return a.start_time < b.start_time;
                  return a.packet_index < b.packet_index;
              });
    return true;
}

bool StreamAnalyzer::match_row(const StreamRow& row, const StreamMatch& match, std::string& error) const {
    const StreamValue* value_ptr = nullptr;
    if (match.field_scope == "beat" || match.field_scope == "any" || match.field_scope.empty()) {
        auto it = row.fields.find(match.field);
        if (it != row.fields.end()) value_ptr = &it->second;
    }
    if (!value_ptr && (match.field_scope == "stable" || match.field_scope == "any" || match.field_scope.empty())) {
        auto it = row.stable_fields.find(match.field);
        if (it != row.stable_fields.end()) value_ptr = &it->second;
    }
    if (!value_ptr) {
        error = "match field not found: " + match.field;
        return false;
    }
    unsigned long long lhs = 0;
    if (!value_u64(*value_ptr, lhs)) return false;
    bool ok = false;
    std::string parse_error;
    unsigned long long value = parse_user_u64(match.value, ok, parse_error);
    if (!ok && match.op != "in_range") {
        error = parse_error.empty() ? "invalid match value: " + match.value : parse_error;
        return false;
    }
    if (match.op == "==") return lhs == value;
    if (match.op == "!=") return lhs != value;
    if (match.op == ">") return lhs > value;
    if (match.op == ">=") return lhs >= value;
    if (match.op == "<") return lhs < value;
    if (match.op == "<=") return lhs <= value;
    if (match.op == "mask_eq") {
        bool mok = false;
        std::string mask_error;
        unsigned long long mask = parse_user_u64(match.mask, mok, mask_error);
        if (!mok) {
            error = mask_error.empty() ? "invalid match mask: " + match.mask : mask_error;
            return false;
        }
        return (lhs & mask) == (value & mask);
    }
    if (match.op == "in_range") {
        bool lok = false, hik = false;
        std::string lo_error, hi_error;
        unsigned long long lo = parse_user_u64(match.lo, lok, lo_error);
        unsigned long long hi = parse_user_u64(match.hi, hik, hi_error);
        if (!lok || !hik) {
            error = !lo_error.empty() ? lo_error : !hi_error.empty() ? hi_error : "invalid in_range bounds";
            return false;
        }
        return lhs >= lo && lhs <= hi;
    }
    error = "unsupported match op: " + match.op;
    return false;
}

Json stream_row_json(const StreamRow& row) {
    Json j;
    j["cycle"] = row.cycle;
    j["time"] = format_time(row.time);
    j["vld"] = row.vld;
    j["rdy"] = row.rdy;
    j["bp"] = row.bp;
    j["sop"] = row.sop;
    j["eop"] = row.eop;
    j["transfer"] = row.transfer;
    j["stall"] = row.stall;
    if (!row.stall_reason.empty()) j["stall_reason"] = row.stall_reason;
    if (row.packet_index >= 0) j["packet_index"] = row.packet_index;
    j["beat_index"] = row.beat_index;
    j["fields"] = fields_json(row.fields);
    if (!row.stable_fields.empty()) j["stable_fields"] = fields_json(row.stable_fields);
    if (!row.channel.bits.empty()) j["channel_id"] = stream_value_json(row.channel);
    return j;
}

Json stream_stall_json(const StreamStallWindow& stall) {
    return Json{{"start_cycle", stall.start_cycle}, {"end_cycle", stall.end_cycle},
                {"start_time", format_time(stall.start_time)}, {"end_time", format_time(stall.end_time)},
                {"cycles", stall.cycles}, {"reason", stall.reason}};
}

Json stream_packet_json(const StreamPacket& packet) {
    Json j{{"packet_index", packet.packet_index},
           {"start_cycle", packet.start_cycle}, {"end_cycle", packet.end_cycle},
           {"start_time", format_time(packet.start_time)}, {"end_time", format_time(packet.end_time)},
           {"beat_count", packet.beat_count},
           {"partial_begin", packet.partial_begin}, {"partial_end", packet.partial_end},
           {"stable_fields", fields_json(packet.stable_fields)},
           {"stable_mismatches", stable_mismatches_json(packet.stable_mismatches)},
           {"beat_fields_preview", beat_preview_json(packet.beats)},
           {"first_fields", fields_json(packet.first_fields)},
           {"last_fields", fields_json(packet.last_fields)}};
    if (!packet.channel.bits.empty()) j["channel_id"] = stream_value_json(packet.channel);
    return j;
}

Json stream_summary_json(const StreamConfig& config, const StreamAnalysis& analysis) {
    Json j;
    j["stream"] = config.name;
    j["sampling_mode"] = "clock_edge";
    j["clock"] = config.clock_sample.clock;
    j["edge"] = clock_edge_kind_text(config.clock_sample.edge);
    if (config.clock_sample.edge != ClockEdgeKind::Negedge)
        j["sample_point"] = clock_sample_point_text(config.clock_sample.sample_point);
    j["sample_time_semantics"] = "time is sample_time";
    j["handshake"] = stream_handshake_text(config);
    j["packet_enabled"] = stream_packet_enabled(config);
    j["clock_edges"] = analysis.clock_edges;
    j["vld_cycles"] = analysis.vld_cycles;
    j["transfer_count"] = analysis.transfer_count;
    j["stall_cycles"] = analysis.stall_cycles;
    j["stall_windows"] = analysis.stalls.size();
    j["packet_count"] = analysis.packet_count;
    j["control_xz_count"] = analysis.control_xz_count;
    j["data_xz_count"] = analysis.data_xz_count;
    j["ready_bp_conflict_count"] = analysis.ready_bp_conflict_count;
    j["stable_mismatch_count"] = analysis.stable_mismatch_count;
    j["truncated"] = analysis.truncated;
    j["response_truncated"] = analysis.truncated;
    j["retained_transfer_count"] = analysis.transfers.size();
    j["analysis_complete"] = analysis.analysis_complete;
    j["truncation_scope"] = analysis.truncated ? Json("response_rows") : Json(nullptr);
    j["requested_range"] = {{"begin", format_time(analysis.requested_begin)},
                             {"end", format_time(analysis.requested_end)}};
    j["scanned_range"] = {{"begin", analysis.has_scanned_samples
        ? Json(format_time(analysis.scanned_begin)) : Json(nullptr)},
                           {"end", analysis.has_scanned_samples
        ? Json(format_time(analysis.scanned_end)) : Json(nullptr)}};
    if (analysis.has_transfer_evidence) {
        j["first_transfer_time"] = format_time(analysis.first_transfer.time);
        j["last_transfer_time"] = format_time(analysis.last_transfer.time);
    }
    if (!analysis.stalls.empty()) {
        j["first_stall_time"] = format_time(analysis.stalls.front().start_time);
        j["last_stall_time"] = format_time(analysis.stalls.back().start_time);
    }
    return j;
}

} // namespace xdebug_waveform
