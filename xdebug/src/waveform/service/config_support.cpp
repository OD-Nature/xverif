#include "action_support.h"
#include "../protocol/protocol.h"
#include <cctype>
#include <climits>
#include <cstdlib>

namespace xdebug_waveform {

namespace {

bool parse_clock_sample_config(const Json& j,
                               const char* owner,
                               ClockSampleSpec& spec,
                               std::string& err) {
    static const char* legacy[] = {"clk", "sampling", "clock_edge", "posedge", "sample_offset", nullptr};
    for (int i = 0; legacy[i]; ++i) {
        if (j.contains(legacy[i])) {
            err = std::string(owner) + " config uses legacy clock sampling field: " +
                  legacy[i] + "; use clock, edge, and sample_point";
            return false;
        }
    }
    if (!get_string(j, "clock", spec.clock)) {
        err = std::string(owner) + " config requires clock";
        return false;
    }
    if (!parse_clock_edge_kind(string_or(j, "edge", "negedge"), spec.edge, err)) {
        err = std::string("invalid ") + owner + " edge: " + err;
        return false;
    }
    if (j.contains("sample_point")) {
        if (!j["sample_point"].is_string()) {
            err = std::string(owner) + " config sample_point must be before or after";
            return false;
        }
        spec.has_sample_point = true;
        if (!parse_clock_sample_point_kind(j["sample_point"].get<std::string>(),
                                           spec.sample_point,
                                           err)) {
            err = std::string("invalid ") + owner + " sample_point: " + err;
            return false;
        }
    }
    if (spec.edge == ClockEdgeKind::Negedge && spec.has_sample_point) {
        err = std::string(owner) + " config sample_point is only valid with edge:posedge or edge:dual";
        return false;
    }
    return true;
}

} // namespace

bool parse_apb_config(const Json& j, ApbConfig& c, std::string& err) {
    auto get = [&j](const char* key) -> std::string {
        auto it = j.find(key);
        return it != j.end() && it->is_string() ? it->get<std::string>() : "";
    };
    c.paddr = get("paddr");
    c.pwdata = get("pwdata");
    c.prdata = get("prdata");
    c.pwrite = get("pwrite");
    c.penable = get("penable");
    c.psel = get("psel");
    c.pready = get("pready");
    c.pslverr = get("pslverr");
    if (!j.contains("reset") || !parse_reset_config(j["reset"], c.reset, err)) return false;
    if (!parse_clock_sample_config(j, "APB", c.clock_sample, err)) return false;
    if (c.paddr.empty() || c.pwdata.empty() || c.prdata.empty() || c.pwrite.empty() ||
        c.penable.empty() || c.psel.empty() || c.clock_sample.clock.empty()) {
        err = "missing required APB config field";
        return false;
    }
    return true;
}

Json apb_config_json(const ApbConfig& c) {
    Json j = {
        {"name", c.name}, {"paddr", c.paddr}, {"pwdata", c.pwdata}, {"prdata", c.prdata},
        {"pwrite", c.pwrite}, {"penable", c.penable}, {"psel", c.psel},
        {"clock", c.clock_sample.clock}, {"reset", reset_config_json(c.reset)},
        {"edge", clock_edge_kind_text(c.clock_sample.edge)}
    };
    if (c.clock_sample.edge != ClockEdgeKind::Negedge)
        j["sample_point"] = clock_sample_point_text(c.clock_sample.sample_point);
    if (!c.pready.empty()) j["pready"] = c.pready;
    if (!c.pslverr.empty()) j["pslverr"] = c.pslverr;
    return j;
}

bool parse_axi_config(const Json& j, AxiConfig& c, std::string& err) {
    auto get = [&j](const char* key) -> std::string {
        auto it = j.find(key);
        return it != j.end() && it->is_string() ? it->get<std::string>() : "";
    };
    c.awaddr = get("awaddr"); c.awid = get("awid"); c.awlen = get("awlen");
    c.awsize = get("awsize"); c.awburst = get("awburst"); c.awvalid = get("awvalid");
    c.awready = get("awready"); c.wdata = get("wdata"); c.wstrb = get("wstrb");
    c.wlast = get("wlast"); c.wvalid = get("wvalid"); c.wready = get("wready");
    c.bid = get("bid"); c.bresp = get("bresp"); c.bvalid = get("bvalid"); c.bready = get("bready");
    c.araddr = get("araddr"); c.arid = get("arid"); c.arlen = get("arlen");
    c.arsize = get("arsize"); c.arburst = get("arburst"); c.arvalid = get("arvalid");
    c.arready = get("arready"); c.rid = get("rid"); c.rdata = get("rdata");
    c.rresp = get("rresp"); c.rlast = get("rlast"); c.rvalid = get("rvalid");
    c.rready = get("rready");
    if (!j.contains("reset") || !parse_reset_config(j["reset"], c.reset, err)) return false;
    if (!parse_clock_sample_config(j, "AXI", c.clock_sample, err)) return false;
    if (c.awaddr.empty() || c.awid.empty() || c.awlen.empty() || c.awsize.empty() ||
        c.awburst.empty() || c.awvalid.empty() || c.awready.empty() || c.wdata.empty() ||
        c.wstrb.empty() || c.wlast.empty() || c.wvalid.empty() || c.wready.empty() ||
        c.bid.empty() || c.bresp.empty() || c.bvalid.empty() || c.bready.empty() ||
        c.araddr.empty() || c.arid.empty() || c.arlen.empty() || c.arsize.empty() ||
        c.arburst.empty() || c.arvalid.empty() || c.arready.empty() || c.rid.empty() ||
        c.rdata.empty() || c.rresp.empty() || c.rlast.empty() || c.rvalid.empty() ||
        c.rready.empty() || c.clock_sample.clock.empty()) {
        err = "missing required AXI config field";
        return false;
    }
    return true;
}

Json axi_config_json(const AxiConfig& c) {
    Json j;
    j["name"] = c.name;
    j["awaddr"] = c.awaddr; j["awid"] = c.awid; j["awlen"] = c.awlen;
    j["awsize"] = c.awsize; j["awburst"] = c.awburst; j["awvalid"] = c.awvalid;
    j["awready"] = c.awready; j["wdata"] = c.wdata; j["wstrb"] = c.wstrb;
    j["wlast"] = c.wlast; j["wvalid"] = c.wvalid; j["wready"] = c.wready;
    j["bid"] = c.bid; j["bresp"] = c.bresp; j["bvalid"] = c.bvalid; j["bready"] = c.bready;
    j["araddr"] = c.araddr; j["arid"] = c.arid; j["arlen"] = c.arlen;
    j["arsize"] = c.arsize; j["arburst"] = c.arburst; j["arvalid"] = c.arvalid;
    j["arready"] = c.arready; j["rid"] = c.rid; j["rdata"] = c.rdata;
    j["rresp"] = c.rresp; j["rlast"] = c.rlast; j["rvalid"] = c.rvalid;
    j["rready"] = c.rready;
    j["clock"] = c.clock_sample.clock;
    j["reset"] = reset_config_json(c.reset);
    j["edge"] = clock_edge_kind_text(c.clock_sample.edge);
    if (c.clock_sample.edge != ClockEdgeKind::Negedge)
        j["sample_point"] = clock_sample_point_text(c.clock_sample.sample_point);
    return j;
}

bool parse_nonnegative_int(const Json& v, int& out) {
    if (!v.is_number_integer()) return false;
    long long n = v.get<long long>();
    if (n < 0 || n > INT_MAX) return false;
    out = static_cast<int>(n);
    return true;
}

bool parse_field_ref(const std::string& text, EventField& field) {
    size_t lb = text.find('[');
    size_t colon = text.find(':', lb == std::string::npos ? 0 : lb);
    size_t rb = text.find(']', colon == std::string::npos ? 0 : colon);
    if (lb == std::string::npos || colon == std::string::npos ||
        rb == std::string::npos || rb != text.size() - 1) return false;
    field.signal_alias = text.substr(0, lb);
    char* end = nullptr;
    long left = strtol(text.substr(lb + 1, colon - lb - 1).c_str(), &end, 10);
    if (!end || *end != '\0' || left < 0 || left > INT_MAX) return false;
    long right = strtol(text.substr(colon + 1, rb - colon - 1).c_str(), &end, 10);
    if (!end || *end != '\0' || right < 0 || right > INT_MAX) return false;
    field.left = static_cast<int>(left);
    field.right = static_cast<int>(right);
    return !field.signal_alias.empty();
}

bool parse_event_config(const Json& j, EventConfig& c, std::string& err) {
    if (!parse_clock_sample_config(j, "event", c.clock_sample, err)) return false;
    if (j.contains("rst_n")) {
        err = "event config field rst_n is not supported; use reset.signal and reset.polarity";
        return false;
    }
    c.has_reset = j.contains("reset");
    if (c.has_reset && !parse_reset_config(j["reset"], c.reset, err)) return false;
    auto sig_it = j.find("signals");
    if (sig_it == j.end() || !sig_it->is_object() || sig_it->empty()) {
        err = "event config requires non-empty signals object";
        return false;
    }
    for (auto it = sig_it->begin(); it != sig_it->end(); ++it) {
        if (!it.value().is_string()) {
            err = "event signal alias must map to string path: " + it.key();
            return false;
        }
        c.signals[it.key()] = it.value().get<std::string>();
    }
    auto fields_it = j.find("fields");
    if (fields_it != j.end()) {
        if (!fields_it->is_object()) {
            err = "event fields must be object";
            return false;
        }
        for (auto it = fields_it->begin(); it != fields_it->end(); ++it) {
            EventField f;
            if (it.value().is_string()) {
                if (!parse_field_ref(it.value().get<std::string>(), f)) {
                    err = "invalid field slice: " + it.key();
                    return false;
                }
            } else if (it.value().is_object()) {
                auto left_it = it.value().find("left");
                auto right_it = it.value().find("right");
                if (!get_string(it.value(), "signal", f.signal_alias) ||
                    left_it == it.value().end() || right_it == it.value().end() ||
                    !parse_nonnegative_int(*left_it, f.left) ||
                    !parse_nonnegative_int(*right_it, f.right)) {
                    err = "invalid field object: " + it.key();
                    return false;
                }
            } else {
                err = "invalid field definition: " + it.key();
                return false;
            }
            if (c.signals.find(f.signal_alias) == c.signals.end()) {
                err = "field references unknown signal alias: " + f.signal_alias;
                return false;
            }
            c.fields[it.key()] = f;
        }
    }
    return true;
}

Json event_config_json(const EventConfig& c) {
    Json j;
    j["name"] = c.name;
    j["clock"] = c.clock_sample.clock;
    if (c.has_reset) j["reset"] = reset_config_json(c.reset);
    j["edge"] = clock_edge_kind_text(c.clock_sample.edge);
    if (c.clock_sample.edge != ClockEdgeKind::Negedge)
        j["sample_point"] = clock_sample_point_text(c.clock_sample.sample_point);
    j["signals"] = c.signals;
    Json fields = Json::object();
    for (const auto& kv : c.fields) {
        fields[kv.first] = {
            {"signal", kv.second.signal_alias},
            {"left", kv.second.left},
            {"right", kv.second.right}
        };
    }
    j["fields"] = fields;
    return j;
}

bool load_config_json_arg(const Json& args, Json& config, std::string& err) {
    auto cfg_it = args.find("config");
    if (cfg_it != args.end()) {
        if (!cfg_it->is_object()) {
            err = "args.config must be an object";
            return false;
        }
        config = *cfg_it;
        return true;
    }
    std::string path;
    if (!get_string(args, "config_path", path)) {
        err = "missing args.config or args.config_path";
        return false;
    }
    std::string text;
    if (!load_text_file(path, text)) {
        err = "cannot read config_path: " + path;
        return false;
    }
    try {
        config = Json::parse(text);
    } catch (const std::exception& e) {
        err = std::string("failed to parse config_path: ") + e.what();
        return false;
    }
    return true;
}

char fmt_char(const Json& args) {
    std::string fmt = string_or(args, "format", "hex");
    if (fmt == "binary" || fmt == "bin") return 'B';
    if (fmt == "decimal" || fmt == "dec") return 'D';
    return 'H';
}

std::string arg_text(const Json& v) {
    if (v.is_string()) return v.get<std::string>();
    if (v.is_number_integer()) return std::to_string(v.get<long long>());
    if (v.is_number_unsigned()) return std::to_string(v.get<unsigned long long>());
    return v.dump();
}

} // namespace xdebug_waveform
