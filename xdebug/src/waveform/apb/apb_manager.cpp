#include "apb_manager.h"
#include "../common/xdebug_waveform_paths.h"
#include "json.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <sys/file.h>

namespace xdebug_waveform {

using Json = nlohmann::ordered_json;

ApbManager::ApbManager() {
}

ApbManager::~ApbManager() {
}

static bool lock_file(int fd) {
    return flock(fd, LOCK_EX) == 0;
}

static bool unlock_file(int fd) {
    return flock(fd, LOCK_UN) == 0;
}

static Json apb_to_json(const ApbConfig& c) {
    Json j = {
        {"name", c.name},
        {"paddr", c.paddr},
        {"pwdata", c.pwdata},
        {"prdata", c.prdata},
        {"pwrite", c.pwrite},
        {"penable", c.penable},
        {"psel", c.psel},
        {"pready", c.pready},
        {"pslverr", c.pslverr},
        {"clock", c.clock_sample.clock},
        {"reset", reset_config_json(c.reset)},
        {"edge", clock_edge_kind_text(c.clock_sample.edge)}
    };
    if (c.clock_sample.edge != ClockEdgeKind::Negedge)
        j["sample_point"] = clock_sample_point_text(c.clock_sample.sample_point);
    return j;
}

static bool json_to_apb(const Json& j, ApbConfig& c) {
    if (!j.is_object()) return false;
    if (j.contains("sample_offset")) return false;
    c.name = j.value("name", "");
    c.paddr = j.value("paddr", "");
    c.pwdata = j.value("pwdata", "");
    c.prdata = j.value("prdata", "");
    c.pwrite = j.value("pwrite", "");
    c.penable = j.value("penable", "");
    c.psel = j.value("psel", "");
    c.pready = j.value("pready", "");
    c.pslverr = j.value("pslverr", "");
    c.clock_sample.clock = j.value("clock", "");
    std::string edge_error;
    if (!j.contains("reset") || !parse_reset_config(j["reset"], c.reset, edge_error)) return false;
    if (!parse_clock_edge_kind(j.value("edge", "negedge"), c.clock_sample.edge, edge_error)) {
        return false;
    }
    if (j.contains("sample_point")) {
        if (!j["sample_point"].is_string()) return false;
        c.clock_sample.has_sample_point = true;
        if (!parse_clock_sample_point_kind(j["sample_point"].get<std::string>(),
                                           c.clock_sample.sample_point,
                                           edge_error)) return false;
    }
    if (c.clock_sample.edge == ClockEdgeKind::Negedge && c.clock_sample.has_sample_point)
        return false;
    return !c.name.empty();
}

bool ApbManager::parse_legacy_line(const char* line, ApbConfig& config, int& session_id) {
    char buf[10][1024];
    int n = sscanf(line, "%d|%1023[^|]|%1023[^|]|%1023[^|]|%1023[^|]|%1023[^|]|%1023[^|]|%1023[^|]|%1023[^|]|%1023[^|]|%1023[^|\n]",
                   &session_id,
                   buf[0], buf[1], buf[2], buf[3], buf[4],
                   buf[5], buf[6], buf[7], buf[8], buf[9]);
    if (n != 11) return false;
    config.name    = buf[0];
    config.paddr   = buf[1];
    config.pwdata  = buf[2];
    config.prdata  = buf[3];
    config.pwrite  = buf[4];
    config.penable = buf[5];
    config.psel    = buf[6];
    config.clock_sample.clock = buf[7];
    config.reset.signal = buf[8];
    config.reset.polarity = ResetPolarity::ActiveLow;
    config.clock_sample.edge = (strcmp(buf[9], "posedge") == 0)
        ? ClockEdgeKind::Posedge : ClockEdgeKind::Negedge;
    return true;
}

bool ApbManager::migrate_legacy(const std::string& session_id, std::vector<ApbConfig>& configs) {
    (void)session_id;
    (void)configs;
    return false;
}

bool ApbManager::load_session(const std::string& session_id, std::vector<ApbConfig>& configs) {
    configs.clear();
    int fd = open(xdebug_waveform_apb_path(session_id).c_str(), O_RDONLY);
    if (fd < 0) return migrate_legacy(session_id, configs);
    if (!lock_file(fd)) {
        close(fd);
        return false;
    }
    FILE* fp = fdopen(fd, "r");
    if (!fp) {
        unlock_file(fd);
        close(fd);
        return false;
    }
    std::string text;
    char buf[4096];
    while (fgets(buf, sizeof(buf), fp)) text += buf;
    fclose(fp);
    if (text.empty()) return true;
    try {
        Json root = Json::parse(text);
        if (!root.is_object() || !root.value("configs", Json::array()).is_array()) return true;
        for (const auto& item : root["configs"]) {
            ApbConfig config;
            if (json_to_apb(item, config)) configs.push_back(config);
        }
    } catch (...) {
        return false;
    }
    return true;
}

bool ApbManager::save_session(const std::string& session_id, const std::vector<ApbConfig>& configs) {
    if (!xdebug_waveform_ensure_session_dir(session_id)) return false;
    int fd = open(xdebug_waveform_apb_path(session_id).c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return false;
    if (!lock_file(fd)) {
        close(fd);
        return false;
    }
    Json root;
    root["version"] = 1;
    root["configs"] = Json::array();
    for (const auto& config : configs) root["configs"].push_back(apb_to_json(config));
    std::string data = root.dump(2) + "\n";
    bool ok = write(fd, data.c_str(), data.size()) == static_cast<ssize_t>(data.size());
    unlock_file(fd);
    close(fd);
    return ok;
}

bool ApbManager::create_apb(const std::string& session_id, const ApbConfig& config) {
    std::vector<ApbConfig> configs;
    load_session(session_id, configs);
    for (const auto& c : configs) {
        if (c.name == config.name) return false;
    }
    configs.push_back(config);
    return save_session(session_id, configs);
}

bool ApbManager::delete_apb(const std::string& session_id, const std::string& name) {
    std::vector<ApbConfig> configs;
    load_session(session_id, configs);
    std::vector<ApbConfig> out;
    bool found = false;
    for (const auto& c : configs) {
        if (c.name == name) {
            found = true;
            continue;
        }
        out.push_back(c);
    }
    return found && save_session(session_id, out);
}

bool ApbManager::get_apb(const std::string& session_id, const std::string& name, ApbConfig& config) {
    std::vector<ApbConfig> configs;
    load_session(session_id, configs);
    for (const auto& c : configs) {
        if (c.name == name) {
            config = c;
            return true;
        }
    }
    return false;
}

bool ApbManager::get_latest_apb(const std::string& session_id, std::string& name) {
    std::vector<ApbConfig> configs;
    load_session(session_id, configs);
    if (configs.empty()) return false;
    name = configs.back().name;
    return true;
}

std::vector<ApbConfig> ApbManager::list_all(const std::string& session_id) {
    std::vector<ApbConfig> configs;
    load_session(session_id, configs);
    return configs;
}

} // namespace xdebug_waveform
