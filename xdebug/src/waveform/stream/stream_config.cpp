#include "stream_config.h"

#include <cctype>
#include <set>

namespace xdebug_waveform {

namespace {

bool get_string(const Json& obj, const char* key, std::string& out) {
    auto it = obj.find(key);
    if (it == obj.end()) return false;
    if (!it->is_string()) return false;
    out = it->get<std::string>();
    return true;
}

bool get_bool(const Json& obj, const char* key, bool& out) {
    auto it = obj.find(key);
    if (it == obj.end()) return false;
    if (!it->is_boolean()) return false;
    out = it->get<bool>();
    return true;
}

bool parse_field_map(const Json& item,
                     const std::string& stream_name,
                     const char* key,
                     std::map<std::string, std::string>& out,
                     std::string& error) {
    auto fields_it = item.find(key);
    if (fields_it == item.end()) return true;
    if (!fields_it->is_object()) {
        error = "stream " + stream_name + " " + key + " must be an object";
        return false;
    }
    for (auto it = fields_it->begin(); it != fields_it->end(); ++it) {
        if (!stream_field_name_valid(it.key())) {
            error = "invalid or reserved data field name: " + it.key();
            return false;
        }
        if (!it.value().is_string() || it.value().get<std::string>().empty()) {
            error = std::string(key) + " field " + it.key() + " must map to a non-empty expression";
            return false;
        }
        if (out.find(it.key()) != out.end()) {
            error = std::string("duplicate field name in ") + key + ": " + it.key();
            return false;
        }
        out[it.key()] = it.value().get<std::string>();
    }
    return true;
}

bool is_ident_start(char c) {
    return std::isalpha(static_cast<unsigned char>(c)) || c == '_';
}

bool is_ident_char(char c) {
    return std::isalnum(static_cast<unsigned char>(c)) || c == '_';
}

} // namespace

bool stream_name_valid(const std::string& name) {
    if (name.empty() || !is_ident_start(name[0])) return false;
    for (char c : name) {
        if (!is_ident_char(c)) return false;
    }
    return true;
}

bool stream_field_name_valid(const std::string& name) {
    static const std::set<std::string> reserved = {
        "time", "cycle", "vld", "rdy", "bp", "sop", "eop",
        "transfer", "stall", "packet_index", "beat_index"
    };
    return stream_name_valid(name) && reserved.find(name) == reserved.end();
}

bool parse_stream_config_json(const Json& item, StreamConfig& config, std::string& error) {
    if (!item.is_object()) {
        error = "stream config must be an object";
        return false;
    }
    config = StreamConfig();
    get_string(item, "name", config.name);
    get_string(item, "clock", config.clock);
    get_string(item, "reset", config.reset);
    get_string(item, "vld", config.vld);
    get_string(item, "rdy", config.rdy);
    get_string(item, "bp", config.bp);
    get_string(item, "sop", config.sop);
    get_string(item, "eop", config.eop);
    get_string(item, "data", config.data);
    get_string(item, "channel_id", config.channel_id);
    get_string(item, "channel_id_valid", config.channel_id_valid);
    get_bool(item, "allow_interleaving", config.allow_interleaving);
    get_string(item, "description", config.description);

    std::string edge;
    if (!get_string(item, "clock_edge", edge)) get_string(item, "edge", edge);
    if (edge.empty() || edge == "posedge") config.posedge = true;
    else if (edge == "negedge") config.posedge = false;
    else {
        error = "invalid clock_edge for stream " + config.name + ": " + edge;
        return false;
    }

    if (!stream_name_valid(config.name)) {
        error = "invalid stream name: " + config.name;
        return false;
    }
    if (config.clock.empty()) {
        error = "stream " + config.name + " requires clock";
        return false;
    }
    if (config.vld.empty()) {
        error = "stream " + config.name + " requires vld";
        return false;
    }

    if (config.channel_id_valid.empty()) config.channel_id_valid = "every_beat";
    if (config.channel_id_valid != "sop" &&
        config.channel_id_valid != "eop" &&
        config.channel_id_valid != "every_beat") {
        error = "stream " + config.name + " channel_id_valid must be sop, eop, or every_beat";
        return false;
    }
    if (!parse_field_map(item, config.name, "data_fields", config.data_fields, error)) return false;
    if (!parse_field_map(item, config.name, "stable_fields", config.stable_fields, error)) return false;
    if (!parse_field_map(item, config.name, "beat_fields", config.beat_fields, error)) return false;
    for (const auto& kv : config.data_fields) {
        if (config.beat_fields.find(kv.first) != config.beat_fields.end()) {
            error = "duplicate legacy data_fields and beat_fields field name: " + kv.first;
            return false;
        }
    }
    if (!config.data.empty()) {
        if (config.beat_fields.find("data") != config.beat_fields.end() ||
            config.data_fields.find("data") != config.data_fields.end()) {
            error = "duplicate legacy data field name: data";
            return false;
        }
    }
    for (const auto& kv : config.stable_fields) {
        if (config.beat_fields.find(kv.first) != config.beat_fields.end() ||
            config.data_fields.find(kv.first) != config.data_fields.end() ||
            (!config.data.empty() && kv.first == "data")) {
            error = "stable_fields and beat_fields must not share field name: " + kv.first;
            return false;
        }
    }
    if (config.data.empty() && config.data_fields.empty() &&
        config.beat_fields.empty() && config.stable_fields.empty()) {
        error = "stream " + config.name + " requires data, data_fields, stable_fields, or beat_fields";
        return false;
    }
    if ((config.sop.empty()) != (config.eop.empty())) {
        error = "stream " + config.name + " requires sop and eop to be configured together";
        return false;
    }
    if ((config.channel_id_valid == "sop" || config.channel_id_valid == "eop") && !stream_packet_enabled(config)) {
        error = "stream " + config.name + " channel_id_valid=" + config.channel_id_valid + " requires sop/eop";
        return false;
    }
    if ((config.channel_id_valid == "sop" || config.channel_id_valid == "eop") && config.channel_id.empty()) {
        error = "stream " + config.name + " channel_id_valid=" + config.channel_id_valid + " requires channel_id";
        return false;
    }
    if (config.allow_interleaving) {
        if (!stream_packet_enabled(config)) {
            error = "stream " + config.name + " allow_interleaving requires sop/eop";
            return false;
        }
        if (config.channel_id.empty()) {
            error = "stream " + config.name + " allow_interleaving requires channel_id";
            return false;
        }
        if (config.channel_id_valid != "every_beat") {
            error = "stream " + config.name + " allow_interleaving requires channel_id_valid=every_beat";
            return false;
        }
    }
    return true;
}

Json stream_config_json(const StreamConfig& c) {
    Json j;
    j["name"] = c.name;
    j["clock"] = c.clock;
    j["clock_edge"] = c.posedge ? "posedge" : "negedge";
    if (!c.reset.empty()) j["reset"] = c.reset;
    j["vld"] = c.vld;
    if (!c.rdy.empty()) j["rdy"] = c.rdy;
    if (!c.bp.empty()) j["bp"] = c.bp;
    if (!c.sop.empty()) j["sop"] = c.sop;
    if (!c.eop.empty()) j["eop"] = c.eop;
    if (!c.data.empty()) j["data"] = c.data;
    if (!c.data_fields.empty()) {
        j["data_fields"] = Json::object();
        for (const auto& kv : c.data_fields) j["data_fields"][kv.first] = kv.second;
    }
    if (!c.stable_fields.empty()) {
        j["stable_fields"] = Json::object();
        for (const auto& kv : c.stable_fields) j["stable_fields"][kv.first] = kv.second;
    }
    if (!c.beat_fields.empty()) {
        j["beat_fields"] = Json::object();
        for (const auto& kv : c.beat_fields) j["beat_fields"][kv.first] = kv.second;
    }
    if (!c.channel_id.empty()) j["channel_id"] = c.channel_id;
    j["channel_id_valid"] = c.channel_id_valid.empty() ? "every_beat" : c.channel_id_valid;
    j["allow_interleaving"] = c.allow_interleaving;
    if (!c.description.empty()) j["description"] = c.description;
    return j;
}

std::string stream_handshake_text(const StreamConfig& c) {
    if (!c.rdy.empty() && !c.bp.empty()) return "vld/rdy/bp";
    if (!c.rdy.empty()) return "vld/rdy";
    if (!c.bp.empty()) return "vld/bp";
    return "vld";
}

bool stream_packet_enabled(const StreamConfig& c) {
    return !c.sop.empty() && !c.eop.empty();
}

} // namespace xdebug_waveform
