#include "reset_config.h"

#include <cctype>

namespace xdebug_waveform {
namespace {

bool known_level(const std::string& raw_value, bool& high) {
    std::string bits;
    size_t quote = raw_value.find('\'');
    const std::string payload = quote == std::string::npos
        ? raw_value : raw_value.substr(quote + 1);
    for (char c : payload) {
        if (c == '0' || c == '1') bits.push_back(c);
        else if (c == 'x' || c == 'X' || c == 'z' || c == 'Z') return false;
    }
    if (bits.size() != 1) return false;
    high = bits == "1";
    return true;
}

} // namespace

bool parse_reset_config(const nlohmann::ordered_json& value, ResetConfig& config,
                        std::string& error) {
    if (!value.is_object()) {
        error = "reset must be an object with signal and polarity";
        return false;
    }
    if (value.size() != 2 || !value.contains("signal") || !value.contains("polarity") ||
        !value["signal"].is_string() || !value["polarity"].is_string() ||
        value["signal"].get<std::string>().empty()) {
        error = "reset requires exactly non-empty signal and polarity";
        return false;
    }
    const std::string polarity = value["polarity"].get<std::string>();
    if (polarity == "active_low") config.polarity = ResetPolarity::ActiveLow;
    else if (polarity == "active_high") config.polarity = ResetPolarity::ActiveHigh;
    else {
        error = "reset.polarity must be active_low or active_high";
        return false;
    }
    config.signal = value["signal"].get<std::string>();
    return true;
}

nlohmann::ordered_json reset_config_json(const ResetConfig& config) {
    return {{"signal", config.signal},
            {"polarity", config.polarity == ResetPolarity::ActiveLow
                             ? "active_low" : "active_high"}};
}

bool reset_is_active(const ResetConfig& config, const std::string& raw_value) {
    bool high = false;
    if (!known_level(raw_value, high)) return true;
    return config.polarity == ResetPolarity::ActiveHigh ? high : !high;
}

} // namespace xdebug_waveform
