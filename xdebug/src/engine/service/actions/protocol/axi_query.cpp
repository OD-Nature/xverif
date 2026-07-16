#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "protocol_action_helpers.h"

#include "waveform/apb/apb_manager.h"
#include "waveform/apb/apb_analyzer.h"
#include "waveform/axi/axi_manager.h"
#include "waveform/axi/axi_analyzer.h"
#include "waveform/axi/axi_exporter.h"
#include "waveform/axi/axi_transaction_json.h"
#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/value/logic_value.h"
#include "core/npi/time_contract.h"

#include <fstream>
#include <memory>
#include <ctime>
#include <sstream>

namespace xdebug_design {
namespace {

static bool parse_user_uint64_literal(const std::string& text,
                                      uint64_t& out,
                                      std::string& err) {
    xdebug_waveform::LogicValue value = xdebug_waveform::parse_user_logic_literal(text);
    if (!value.valid) {
        err = value.error;
        return false;
    }
    if (xdebug_waveform::logic_value_has_xz(value) || value.bits.size() > 64) {
        err = "value literal must be known and at most 64 bits: " + text;
        return false;
    }
    out = 0;
    for (char c : value.bits) {
        out <<= 1ULL;
        if (c == '1') out |= 1ULL;
    }
    return true;
}
class AxiQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.query"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        const bool include_data = a.value("output", Json::object()).value("include_data", false);
        std::string name = a.value("name", "");
        if (name.empty()) return protocol_missing_name_error(action_name(), "axi");

        AxiConfig cfg; std::string err;
        if (!ensure_axi_analyzed(name, cfg, err)) {
            if (err.rfind("AXI config not found:", 0) == 0)
                return protocol_config_not_found_error(action_name(), "axi", name);
            else if (!g_axi_analyzer.last_cache_error().empty())
                return make_analysis_cache_error(
                    g_axi_analyzer.last_cache_error());
            else
                return protocol_analyze_error(action_name(), "axi", name, err);
        }

        std::string dir = a.value("direction", "write");
        bool is_write = (dir != "read");
        std::string addr_str = a.value("address", a.value("addr", ""));
        std::string id_str = a.value("id", "");
        Json query = a.value("query", Json::object());
        const std::string channel = query.value("channel", std::string());
        const std::string handshake_time_text = query.value("handshake_time", std::string());
        int num = query.value("index", -1);
        int limit = query.value("line_limit", -1);
        bool last = a.value("last", false);

        if (!channel.empty() || !handshake_time_text.empty()) {
            if (channel.empty() || handshake_time_text.empty())
                return protocol_invalid_arg_error(
                    action_name(), "args.query",
                    "query.channel and query.handshake_time must be provided together",
                    "channel plus canonical time string");
            if (a.contains("direction") || a.contains("address") || a.contains("addr") ||
                a.contains("id") || a.contains("last") || query.contains("index") ||
                query.contains("line_limit"))
                return protocol_invalid_arg_error(
                    action_name(), "args.query",
                    "handshake query cannot be combined with transaction selectors",
                    "only query.channel, query.handshake_time, and optional output.include_data");
            npiFsdbTime handshake_time = 0;
            std::string time_error;
            if (!parse_user_time(handshake_time_text.c_str(), false, handshake_time, time_error))
                return protocol_invalid_arg_error(action_name(), "args.query.handshake_time",
                                                  time_error, "canonical time string such as 120ns");
            AxiHandshakeMatch match;
            const bool found = g_axi_analyzer.get_by_handshake(name, channel, handshake_time, match);
            if (!g_axi_analyzer.last_cache_error().empty())
                return make_analysis_cache_error(
                    g_axi_analyzer.last_cache_error());
            Json out;
            out["summary"] = { {"name", name}, {"query_mode", "handshake"}, {"found", found} };
            out["match"] = {
                {"channel", channel},
                {"handshake_time", xdebug_core::format_time(g_fsdb_file, handshake_time)},
            };
            if (found && match.txn)
                out["match"]["direction"] = match.txn->is_write ? "write" : "read";
            if (found && match.beat_index > 0) out["match"]["beat_index"] = match.beat_index;
            if (found && match.txn)
                out["transaction"] = axi_transaction_to_json(g_fsdb_file, *match.txn, include_data);
            return out;
        }

        const AxiTransaction* txn = nullptr;
        bool found = false;
        if (!addr_str.empty()) {
            uint64_t addr = 0;
            std::string parse_err;
            if (!parse_user_uint64_literal(addr_str, addr, parse_err))
                return protocol_invalid_arg_error(action_name(), "args.address",
                                                  parse_err,
                                                  "known integer or SystemVerilog literal address");
            if (!id_str.empty()) {
                uint64_t id_value = 0;
                if (!parse_user_uint64_literal(id_str, id_value, parse_err))
                    return protocol_invalid_arg_error(action_name(), "args.id",
                                                      parse_err,
                                                      "known integer or SystemVerilog literal id");
                id_str = std::to_string(id_value);
            }
            if (!g_axi_analyzer.ensure_address_index(name))
                return make_analysis_cache_error(
                    g_axi_analyzer.last_cache_error());
            if (!id_str.empty()) {
                if (num >= 0)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_num(name, addr, id_str.c_str(), (size_t)num, txn)
                                     : g_axi_analyzer.get_read_by_addr_num(name, addr, id_str.c_str(), (size_t)num, txn);
                else if (limit > 0) {
                    Json transactions = Json::array();
                    for (int i = 1; i <= limit; ++i) {
                        const AxiTransaction* item = nullptr;
                        bool ok = is_write ? g_axi_analyzer.get_write_by_addr_num(name, addr, id_str.c_str(), (size_t)i, item)
                                           : g_axi_analyzer.get_read_by_addr_num(name, addr, id_str.c_str(), (size_t)i, item);
                        if (!ok || !item) break;
                        transactions.push_back(axi_transaction_to_json(g_fsdb_file, *item, include_data));
                    }
                    Json out;
                    out["summary"] = {{"name",name},{"direction",dir},{"count",(int)transactions.size()}};
                    out["transactions"] = transactions;
                    return out;
                }
                else if (last)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_last(name, addr, id_str.c_str(), txn)
                                     : g_axi_analyzer.get_read_by_addr_last(name, addr, id_str.c_str(), txn);
                else
                    found = is_write ? g_axi_analyzer.get_write_by_addr(name, addr, id_str.c_str(), txn)
                                     : g_axi_analyzer.get_read_by_addr(name, addr, id_str.c_str(), txn);
            } else {
                if (num >= 0)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_num(name, addr, (size_t)num, txn)
                                     : g_axi_analyzer.get_read_by_addr_num(name, addr, (size_t)num, txn);
                else if (limit > 0) {
                    Json transactions = Json::array();
                    for (int i = 1; i <= limit; ++i) {
                        const AxiTransaction* item = nullptr;
                        bool ok = is_write ? g_axi_analyzer.get_write_by_addr_num(name, addr, (size_t)i, item)
                                           : g_axi_analyzer.get_read_by_addr_num(name, addr, (size_t)i, item);
                        if (!ok || !item) break;
                        transactions.push_back(axi_transaction_to_json(g_fsdb_file, *item, include_data));
                    }
                    Json out;
                    out["summary"] = {{"name",name},{"direction",dir},{"count",(int)transactions.size()}};
                    out["transactions"] = transactions;
                    return out;
                }
                else if (last)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_last(name, addr, txn)
                                     : g_axi_analyzer.get_read_by_addr_last(name, addr, txn);
                else
                    found = is_write ? g_axi_analyzer.get_write_by_addr(name, addr, txn)
                                     : g_axi_analyzer.get_read_by_addr(name, addr, txn);
            }
        } else if (!id_str.empty()) {
            if (!g_axi_analyzer.ensure_id_index(name))
                return make_analysis_cache_error(
                    g_axi_analyzer.last_cache_error());
            if (num >= 0)
                found = is_write ? g_axi_analyzer.get_write_by_num(name, id_str.c_str(), (size_t)num, txn)
                                 : g_axi_analyzer.get_read_by_num(name, id_str.c_str(), (size_t)num, txn);
            else if (limit > 0) {
                Json transactions = Json::array();
                for (int i = 1; i <= limit; ++i) {
                    const AxiTransaction* item = nullptr;
                    bool ok = is_write ? g_axi_analyzer.get_write_by_num(name, id_str.c_str(), (size_t)i, item)
                                       : g_axi_analyzer.get_read_by_num(name, id_str.c_str(), (size_t)i, item);
                    if (!ok || !item) break;
                    transactions.push_back(axi_transaction_to_json(g_fsdb_file, *item, include_data));
                }
                Json out;
                out["summary"] = {{"name",name},{"direction",dir},{"count",(int)transactions.size()}};
                out["transactions"] = transactions;
                return out;
            }
            else if (last)
                found = is_write ? g_axi_analyzer.get_write_last(name, id_str.c_str(), txn)
                                 : g_axi_analyzer.get_read_last(name, id_str.c_str(), txn);
        } else if (num >= 0) {
            found = is_write ? g_axi_analyzer.get_write_by_num(name, (size_t)num, txn)
                             : g_axi_analyzer.get_read_by_num(name, (size_t)num, txn);
        } else if (limit > 0) {
            Json transactions = Json::array();
            for (int i = 1; i <= limit; ++i) {
                const AxiTransaction* item = nullptr;
                bool ok = is_write ? g_axi_analyzer.get_write_by_num(name, (size_t)i, item)
                                   : g_axi_analyzer.get_read_by_num(name, (size_t)i, item);
                if (!ok || !item) break;
                transactions.push_back(axi_transaction_to_json(g_fsdb_file, *item, include_data));
            }
            Json out;
            out["summary"] = {{"name",name},{"direction",dir},{"count",(int)transactions.size()}};
            out["transactions"] = transactions;
            return out;
        } else if (last) {
            found = is_write ? g_axi_analyzer.get_write_last(name, txn)
                             : g_axi_analyzer.get_read_last(name, txn);
        } else {
            size_t cnt = is_write ? g_axi_analyzer.get_write_count(name)
                                  : g_axi_analyzer.get_read_count(name);
            Json out;
            out["summary"] = {{"name",name},{"direction",dir},{"count",(int)cnt}};
            return out;
        }

        Json out;
        out["summary"] = {{"name",name},{"direction",dir},{"found",found}};
        if (found && txn) {
            out["transaction"] = axi_transaction_to_json(g_fsdb_file, *txn, include_data);
        }
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_axi_query_handler() {
    return std::unique_ptr<EngineActionHandler>(new AxiQueryHandler);
}

}  // namespace xdebug_design
