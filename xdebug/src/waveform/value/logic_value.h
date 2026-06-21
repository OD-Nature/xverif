#pragma once

#include "json.hpp"

#include <string>

namespace xdebug_waveform {

using Json = nlohmann::ordered_json;

struct LogicValue {
    std::string raw;
    std::string display;
    std::string bits;
    int width = 0;
    bool width_reliable = false;
    bool known = true;
    bool has_x = false;
    bool has_z = false;
    bool valid = true;
    std::string error;
};

LogicValue logic_value_from_fsdb_raw(const std::string& raw, char radix,
                                     int width_hint = 0);
LogicValue logic_value_from_bits(const std::string& bits, int width_hint = 0);
LogicValue parse_user_logic_literal(const std::string& text);

Json logic_value_json(const LogicValue& value);
std::string logic_value_compact_string(const LogicValue& value);
std::string logic_value_compare_key(const LogicValue& value);
bool logic_value_has_xz(const LogicValue& value);

bool is_legacy_0x_literal(const std::string& text);
std::string value_format_invalid_message(const std::string& value);

} // namespace xdebug_waveform
