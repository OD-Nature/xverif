#pragma once

#include "json.hpp"

#include <string>

namespace xdebug_waveform {

enum class ResetPolarity {
    ActiveLow,
    ActiveHigh,
};

struct ResetConfig {
    std::string signal;
    ResetPolarity polarity = ResetPolarity::ActiveLow;
};

bool parse_reset_config(const nlohmann::ordered_json& value, ResetConfig& config,
                        std::string& error);
nlohmann::ordered_json reset_config_json(const ResetConfig& config);
bool reset_is_active(const ResetConfig& config, const std::string& raw_value);

} // namespace xdebug_waveform
