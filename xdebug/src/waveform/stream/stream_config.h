#pragma once

#include "../common/clock_sampling.h"

#include "json.hpp"

#include <map>
#include <string>
#include <vector>

namespace xdebug_waveform {

using Json = nlohmann::ordered_json;

struct StreamConfig {
    std::string name;
    std::map<std::string, std::string> signals;
    ClockSampleSpec clock_sample;
    std::string reset;
    std::string vld;
    std::string rdy;
    std::string bp;
    std::string sop;
    std::string eop;
    std::string data;
    std::map<std::string, std::string> packet_stable_fields;
    std::map<std::string, std::string> beat_fields;
    std::string channel_id;
    std::string channel_id_valid = "every_beat";
    bool allow_interleaving = false;
    std::string description;
};

bool stream_name_valid(const std::string& name);
bool stream_field_name_valid(const std::string& name);
bool parse_stream_config_json(const Json& item, StreamConfig& config, std::string& error);
Json stream_config_json(const StreamConfig& config);
std::string stream_handshake_text(const StreamConfig& config);
bool stream_packet_enabled(const StreamConfig& config);

} // namespace xdebug_waveform
