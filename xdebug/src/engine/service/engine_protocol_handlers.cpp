#include "engine_action_handler.h"
#include "engine_action_registry.h"
#include "engine_globals.h"

#include "../../waveform/apb/apb_manager.h"
#include "../../waveform/apb/apb_analyzer.h"
#include "../../waveform/axi/axi_manager.h"
#include "../../waveform/axi/axi_analyzer.h"
#include "../../waveform/axi/axi_exporter.h"
#include "../../waveform/common/xdebug_waveform_paths.h"
#include "../../waveform/value/logic_value.h"

#include <fstream>
#include <memory>
#include <ctime>
#include <sstream>

namespace xdebug_design {
namespace {

// ── helpers ──────────────────────────────────────────────────────────

static bool ensure_apb_analyzed(const std::string& name,
                                 xdebug_waveform::ApbConfig& cfg,
                                 std::string& err) {
    xdebug_waveform::ApbManager am;
    if (!am.get_apb(xdebug_waveform::g_session_id, name, cfg)) {
        err = "APB config not found: " + name;
        return false;
    }
    if (!xdebug_waveform::g_apb_analyzer.analyze(name,
            xdebug_waveform::g_fsdb_file, cfg)) {
        err = "Failed to analyze APB: " + name;
        return false;
    }
    return true;
}

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

// ── APB handlers ──────────────────────────────────────────────────────

class ApbConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        nlohmann::json cfg_j; std::string err_str;
        if (!load_config_from_args(a, cfg_j, err_str))
            return Json({{"error","INVALID_REQUEST"},{"message",err_str}});

        const char* reqs[] = {"clk","rst_n","paddr","psel","penable","pwrite","pwdata","prdata",nullptr};
        for (int i = 0; reqs[i]; ++i) {
            if (!cfg_j.contains(reqs[i]) || !cfg_j[reqs[i]].is_string() ||
                cfg_j[reqs[i]].get<std::string>().empty())
                return Json({{"error","INVALID_REQUEST"},
                    {"message",std::string("missing or empty field: ")+reqs[i]}});
        }

        ApbConfig cfg;
        cfg.name = name;
        cfg.clk = cfg_j["clk"].get<std::string>();
        cfg.rst_n = cfg_j["rst_n"].get<std::string>();
        cfg.paddr = cfg_j["paddr"].get<std::string>();
        cfg.psel = cfg_j["psel"].get<std::string>();
        cfg.penable = cfg_j["penable"].get<std::string>();
        cfg.pwrite = cfg_j["pwrite"].get<std::string>();
        cfg.pwdata = cfg_j["pwdata"].get<std::string>();
        cfg.prdata = cfg_j["prdata"].get<std::string>();
        cfg.pready = cfg_j.value("pready", "");
        cfg.pslverr = cfg_j.value("pslverr", "");
        if (cfg_j.contains("posedge")) cfg.posedge = cfg_j["posedge"].get<bool>();

        ApbManager am;
        if (!am.create_apb(g_session_id, cfg))
            return Json({{"error","CREATE_FAILED"},{"message","failed to save APB config"}});

        Json out;
        out["summary"] = {{"name", name}, {"status", "loaded"}};
        out["name"] = name; out["status"] = "loaded";
        Json cinfo; cinfo["name"] = name; cinfo["clk"] = cfg.clk; cinfo["rst_n"] = cfg.rst_n;
        if (!cfg.pready.empty()) cinfo["pready"] = cfg.pready;
        if (!cfg.pslverr.empty()) cinfo["pslverr"] = cfg.pslverr;
        out["config"] = cinfo;
        return out;
    }
};
class ApbConfigListHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.config.list"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});
        xdebug_waveform::ApbManager am;
        xdebug_waveform::ApbConfig cfg;
        if (!am.get_apb(xdebug_waveform::g_session_id, name, cfg))
            return Json({{"error","CONFIG_NOT_FOUND"}});
        Json out; out["name"] = name;
        out["clk"] = cfg.clk; out["rst_n"] = cfg.rst_n;
        if (!cfg.pready.empty()) out["pready"] = cfg.pready;
        if (!cfg.pslverr.empty()) out["pslverr"] = cfg.pslverr;
        return out;
    }
};

class ApbQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.query"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        ApbConfig cfg; std::string err;
        if (!ensure_apb_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string dir = a.value("direction", "wr");
        bool is_write = (dir != "rd");
        std::string addr_str = a.value("address", a.value("addr", ""));
        int num = a.value("num", -1);
        bool last = a.value("last", false);

        const ApbTransaction* txn = nullptr;
        bool found = false;
        if (!addr_str.empty()) {
            uint64_t addr = 0;
            std::string parse_err;
            if (!parse_user_uint64_literal(addr_str, addr, parse_err))
                return Json({{"error","VALUE_FORMAT_INVALID"},{"message",parse_err}});
            if (num >= 0) {
                found = is_write ? g_apb_analyzer.get_write_by_addr_num(name, addr, (size_t)num, txn)
                                 : g_apb_analyzer.get_read_by_addr_num(name, addr, (size_t)num, txn);
            } else if (last) {
                found = is_write ? g_apb_analyzer.get_write_by_addr_last(name, addr, txn)
                                 : g_apb_analyzer.get_read_by_addr_last(name, addr, txn);
            } else {
                found = is_write ? g_apb_analyzer.get_write_by_addr(name, addr, txn)
                                 : g_apb_analyzer.get_read_by_addr(name, addr, txn);
            }
        } else if (num >= 0) {
            found = is_write ? g_apb_analyzer.get_write_by_num(name, (size_t)num, txn)
                             : g_apb_analyzer.get_read_by_num(name, (size_t)num, txn);
        } else if (last) {
            found = is_write ? g_apb_analyzer.get_write_last(name, txn)
                             : g_apb_analyzer.get_read_last(name, txn);
        } else {
            // No filter — return count
            size_t cnt = is_write ? g_apb_analyzer.get_write_count(name)
                                  : g_apb_analyzer.get_read_count(name);
            Json out;
            out["summary"] = {{"name",name},{"direction",dir},{"count",(int)cnt}};
            out["name"] = name; out["direction"] = dir; out["count"] = (int)cnt;
            return out;
        }

        Json out;
        out["summary"] = {{"name",name},{"direction",dir},{"found",found}};
        out["name"] = name; out["direction"] = dir; out["found"] = found;
        if (found && txn) {
            Json tj;
            tj["time"] = txn->time;
            tj["addr"] = txn->addr;
            tj["data"] = txn->data;
            tj["is_write"] = txn->is_write;
            tj["has_error"] = txn->has_error;
            out["transaction"] = tj;
            out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

class ApbCursorHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.cursor"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        std::string op = a.value("op", "begin");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        ApbConfig cfg; std::string err;
        if (!ensure_apb_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string dir = a.value("direction", "all");
        int filter = (dir == "wr") ? 1 : (dir == "rd") ? 2 : 0;

        const ApbTransaction* txn = nullptr;
        bool ok = false;
        if (op == "begin") ok = g_apb_analyzer.cursor_begin(name, filter, txn);
        else if (op == "next") ok = g_apb_analyzer.cursor_next(name, filter, txn);
        else if (op == "prev" || op == "pre") ok = g_apb_analyzer.cursor_prev(name, filter, txn);
        else if (op == "last") ok = g_apb_analyzer.cursor_last(name, filter, txn);
        else return Json({{"error","INVALID_REQUEST"},{"message","op must be begin/next/prev/last"}});

        Json out;
        out["summary"] = {{"name",name},{"op",op},{"direction",dir},{"found",ok}};
        out["name"] = name; out["op"] = op; out["direction"] = dir; out["found"] = ok;
        if (ok && txn) {
            Json tj;
            tj["time"] = txn->time; tj["addr"] = txn->addr;
            tj["data"] = txn->data; tj["is_write"] = txn->is_write;
            tj["has_error"] = txn->has_error;
            out["transaction"] = tj;
            if (txn->is_write) out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

class AxiConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        nlohmann::json cfg_j; std::string err;
        if (!load_config_from_args(a, cfg_j, err))
            return Json({{"error","INVALID_REQUEST"},{"message",err}});

        // Validate required AXI fields
        const char* reqs[] = {"clk","rst_n",
            "awvalid","awready","awaddr","awid","awlen","awsize","awburst",
            "wvalid","wready","wdata","wstrb","wlast",
            "bvalid","bready","bid","bresp",
            "arvalid","arready","araddr","arid","arlen","arsize","arburst",
            "rvalid","rready","rdata","rid","rresp","rlast",nullptr};
        for (int i = 0; reqs[i]; ++i) {
            if (!cfg_j.contains(reqs[i]) || !cfg_j[reqs[i]].is_string() ||
                cfg_j[reqs[i]].get<std::string>().empty())
                return Json({{"error","INVALID_REQUEST"},
                    {"message",std::string("missing or empty field: ")+reqs[i]}});
        }

        AxiConfig cfg; cfg.name = name;
        cfg.clk = cfg_j["clk"].get<std::string>();
        cfg.rst_n = cfg_j["rst_n"].get<std::string>();
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
        if (cfg_j.contains("posedge")) cfg.posedge = cfg_j["posedge"].get<bool>();

        AxiManager am;
        if (!am.create_axi(g_session_id, cfg))
            return Json({{"error","CREATE_FAILED"},{"message","failed to save AXI config"}});

        Json out;
        out["summary"] = {{"name", name}, {"status", "loaded"}};
        out["name"] = name; out["status"] = "loaded";
        Json cinfo; cinfo["name"] = name; cinfo["clk"] = cfg.clk; cinfo["rst_n"] = cfg.rst_n;
        out["config"] = cinfo;
        return out;
    }
};

class AxiConfigListHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.config.list"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});
        xdebug_waveform::AxiManager am;
        xdebug_waveform::AxiConfig cfg;
        if (!am.get_axi(xdebug_waveform::g_session_id, name, cfg))
            return Json({{"error","CONFIG_NOT_FOUND"}});
        Json out; out["name"] = name;
        out["clk"] = cfg.clk; out["rst_n"] = cfg.rst_n;
        return out;
    }
};

class AxiQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.query"; }
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

        std::string dir = a.value("direction", "wr");
        bool is_write = (dir != "rd");
        std::string addr_str = a.value("address", a.value("addr", ""));
        std::string id_str = a.value("id", "");
        int num = a.value("num", -1);
        bool last = a.value("last", false);

        const AxiTransaction* txn = nullptr;
        bool found = false;
        if (!addr_str.empty()) {
            uint64_t addr = 0;
            std::string parse_err;
            if (!parse_user_uint64_literal(addr_str, addr, parse_err))
                return Json({{"error","VALUE_FORMAT_INVALID"},{"message",parse_err}});
            if (!id_str.empty()) {
                uint64_t id_value = 0;
                if (!parse_user_uint64_literal(id_str, id_value, parse_err))
                    return Json({{"error","VALUE_FORMAT_INVALID"},{"message",parse_err}});
                id_str = std::to_string(id_value);
            }
            if (!id_str.empty()) {
                if (num >= 0)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_num(name, addr, id_str.c_str(), (size_t)num, txn)
                                     : g_axi_analyzer.get_read_by_addr_num(name, addr, id_str.c_str(), (size_t)num, txn);
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
                else if (last)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_last(name, addr, txn)
                                     : g_axi_analyzer.get_read_by_addr_last(name, addr, txn);
                else
                    found = is_write ? g_axi_analyzer.get_write_by_addr(name, addr, txn)
                                     : g_axi_analyzer.get_read_by_addr(name, addr, txn);
            }
        } else if (!id_str.empty()) {
            if (num >= 0)
                found = is_write ? g_axi_analyzer.get_write_by_num(name, id_str.c_str(), (size_t)num, txn)
                                 : g_axi_analyzer.get_read_by_num(name, id_str.c_str(), (size_t)num, txn);
            else if (last)
                found = is_write ? g_axi_analyzer.get_write_last(name, id_str.c_str(), txn)
                                 : g_axi_analyzer.get_read_last(name, id_str.c_str(), txn);
        } else if (num >= 0) {
            found = is_write ? g_axi_analyzer.get_write_by_num(name, (size_t)num, txn)
                             : g_axi_analyzer.get_read_by_num(name, (size_t)num, txn);
        } else if (last) {
            found = is_write ? g_axi_analyzer.get_write_last(name, txn)
                             : g_axi_analyzer.get_read_last(name, txn);
        } else {
            size_t cnt = is_write ? g_axi_analyzer.get_write_count(name)
                                  : g_axi_analyzer.get_read_count(name);
            Json out;
            out["summary"] = {{"name",name},{"direction",dir},{"count",(int)cnt}};
            out["name"] = name; out["direction"] = dir; out["count"] = (int)cnt;
            return out;
        }

        Json out;
        out["summary"] = {{"name",name},{"direction",dir},{"found",found}};
        out["name"] = name; out["direction"] = dir; out["found"] = found;
        if (found && txn) {
            Json tj;
            tj["time"] = txn->addr_time;
            tj["addr"] = txn->addr; tj["id"] = txn->id;
            tj["len"] = txn->len; tj["size"] = txn->size;
            tj["burst"] = txn->burst; tj["is_write"] = txn->is_write;
            if (!txn->data.empty()) { Json da = Json::array(); for (auto& d : txn->data) da.push_back(d); tj["data"] = da; }
            out["transaction"] = tj;
            out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

class AxiCursorHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.cursor"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        std::string op = a.value("op", "begin");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        AxiConfig cfg; std::string err;
        if (!ensure_axi_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string dir = a.value("direction", "all");
        int filter = (dir == "wr") ? 1 : (dir == "rd") ? 2 : 0;

        const AxiTransaction* txn = nullptr;
        bool ok = false;
        if (op == "begin") ok = g_axi_analyzer.cursor_begin(name, filter, txn);
        else if (op == "next") ok = g_axi_analyzer.cursor_next(name, filter, txn);
        else if (op == "prev" || op == "pre") ok = g_axi_analyzer.cursor_prev(name, filter, txn);
        else if (op == "last") ok = g_axi_analyzer.cursor_last(name, filter, txn);
        else return Json({{"error","INVALID_REQUEST"},{"message","op must be begin/next/prev/last"}});

        Json out;
        out["summary"] = {{"name",name},{"op",op},{"direction",dir},{"found",ok}};
        out["name"] = name; out["op"] = op; out["direction"] = dir; out["found"] = ok;
        if (ok && txn) {
            Json tj;
            tj["time"] = txn->addr_time; tj["addr"] = txn->addr; tj["id"] = txn->id;
            tj["len"] = txn->len; tj["is_write"] = txn->is_write;
            out["transaction"] = tj;
            if (txn->is_write) out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

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
        int filter = (dir == "wr") ? 1 : (dir == "rd") ? 2 : 0;
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

class AxiExportHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.export"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        AxiManager am;
        AxiConfig cfg;
        if (!am.get_axi(g_session_id, name, cfg))
            return Json({{"error","CONFIG_NOT_FOUND"},{"message","AXI config not found: " + name}});

        Json tr = a.value("time_range", Json::object());
        std::string begin_s;
        std::string end_s;
        if (tr.is_object()) {
            begin_s = tr.value("begin", tr.value("from", std::string()));
            end_s = tr.value("end", tr.value("to", std::string()));
        }
        if (begin_s.empty()) begin_s = a.value("start", a.value("begin", std::string()));
        if (end_s.empty()) end_s = a.value("end", a.value("to", std::string()));
        if (begin_s.empty() || end_s.empty())
            return Json({{"error","MISSING_FIELD"},{"message","axi.export requires args.time_range.begin/end or args.start/end"}});

        npiFsdbTime begin = 0, end = 0;
        std::string time_err;
        if (!parse_user_time(begin_s.c_str(), false, begin, time_err))
            return Json({{"error","TIME_SPEC_INVALID"},{"message",time_err}});
        if (!parse_user_time(end_s.c_str(), true, end, time_err))
            return Json({{"error","TIME_SPEC_INVALID"},{"message",time_err}});
        if (end < begin)
            return Json({{"error","TIME_SPEC_INVALID"},{"message","axi.export end time is before begin time"}});

        std::string format = a.value("format", std::string("tsv"));
        if (format != "tsv" && format != "csv")
            return Json({{"error","INVALID_REQUEST"},{"message","format must be tsv or csv"}});

        std::string output_prefix = a.value("output_prefix", std::string());
        if (output_prefix.empty()) {
            std::ostringstream oss;
            oss << xdebug_waveform_axi_exports_dir(g_session_id)
                << "/" << name << "_" << begin << "_" << end << "_" << std::time(nullptr);
            output_prefix = oss.str();
        }

        AxiExporter exporter;
        AxiExportResult result;
        result.format = format;
        std::string error;
        if (!exporter.scan(g_fsdb_file, cfg, begin, end, result, error))
            return Json({{"error","ANALYZE_FAILED"},{"message",error}});
        result.format = format;

        std::string write_file, read_file, meta_file;
        if (!exporter.write_files(output_prefix, result, write_file, read_file, meta_file, error))
            return Json({{"error","EXPORT_FAILED"},{"message",error}});

        Json out;
        out["summary"] = {{"name", name},
                          {"write_count", result.writes.size()},
                          {"read_count", result.reads.size()},
                          {"total_count", result.writes.size() + result.reads.size()},
                          {"format", format}};
        out["name"] = name;
        out["format"] = format;
        out["begin"] = format_time(begin);
        out["end"] = format_time(end);
        out["scan_begin"] = format_time(result.scan_begin);
        out["scan_end"] = format_time(result.scan_end);
        out["write_file"] = write_file;
        out["read_file"] = read_file;
        out["meta_file"] = meta_file;
        out["write_count"] = result.writes.size();
        out["read_count"] = result.reads.size();
        out["total_count"] = result.writes.size() + result.reads.size();
        return out;
    }
};

}  // namespace

void register_protocol_handlers(EngineActionRegistry& r) {
    r.add(std::unique_ptr<EngineActionHandler>(new ApbConfigLoadHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ApbConfigListHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ApbQueryHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ApbCursorHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new AxiConfigLoadHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new AxiConfigListHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new AxiQueryHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new AxiCursorHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new AxiAnalysisHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new AxiExportHandler));
}

}  // namespace xdebug_design
