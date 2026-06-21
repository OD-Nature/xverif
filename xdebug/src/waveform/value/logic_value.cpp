#include "logic_value.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>

namespace xdebug_waveform {

namespace {

std::string trim(std::string s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) s.erase(s.begin());
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) s.pop_back();
    return s;
}

std::string clean_lower(const std::string& text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        if (c == '_' || std::isspace(static_cast<unsigned char>(c))) continue;
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

bool decimal_only(const std::string& text) {
    if (text.empty()) return false;
    for (char c : text) {
        if (!std::isdigit(static_cast<unsigned char>(c))) return false;
    }
    return true;
}

std::string dec_to_bits(const std::string& text) {
    std::string clean = clean_lower(text);
    if (!decimal_only(clean)) return std::string();
    char* end = nullptr;
    unsigned long long value = std::strtoull(clean.c_str(), &end, 10);
    if (!end || *end != '\0') return std::string();
    if (value == 0) return "0";
    std::string bits;
    while (value) {
        bits.push_back((value & 1ULL) ? '1' : '0');
        value >>= 1ULL;
    }
    std::reverse(bits.begin(), bits.end());
    return bits;
}

std::string bin_to_bits(const std::string& text) {
    std::string out;
    for (char c : text) {
        if (c == '_' || std::isspace(static_cast<unsigned char>(c))) continue;
        char lower = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (lower != '0' && lower != '1' && lower != 'x' && lower != 'z')
            return std::string();
        out.push_back(lower);
    }
    return out.empty() ? "0" : out;
}

std::string hex_to_bits(const std::string& text) {
    std::string out;
    for (char c : text) {
        if (c == '_' || std::isspace(static_cast<unsigned char>(c))) continue;
        char lower = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (lower == 'x' || lower == 'z') {
            out.append(4, lower);
            continue;
        }
        int v = -1;
        if (lower >= '0' && lower <= '9') v = lower - '0';
        else if (lower >= 'a' && lower <= 'f') v = 10 + lower - 'a';
        if (v < 0) return std::string();
        for (int bit = 3; bit >= 0; --bit) out.push_back((v & (1 << bit)) ? '1' : '0');
    }
    return out.empty() ? "0" : out;
}

std::string bits_to_hex(std::string bits) {
    bits = clean_lower(bits);
    if (bits.empty()) return "0";
    size_t pad = (4 - bits.size() % 4) % 4;
    bits.insert(bits.begin(), pad, '0');
    static const char* hex = "0123456789abcdef";
    std::string out;
    for (size_t i = 0; i < bits.size(); i += 4) {
        bool has_x = false;
        bool has_z = false;
        int value = 0;
        for (size_t j = 0; j < 4; ++j) {
            char c = bits[i + j];
            if (c == 'x') has_x = true;
            else if (c == 'z') has_z = true;
            value = (value << 1) | (c == '1' ? 1 : 0);
        }
        if (has_x) out.push_back('x');
        else if (has_z) out.push_back('z');
        else out.push_back(hex[value]);
    }
    return out.empty() ? "0" : out;
}

void apply_width(LogicValue& value, int width_hint) {
    if (width_hint <= 0) return;
    value.width = width_hint;
    value.width_reliable = true;
    if (value.bits.empty()) return;
    if (static_cast<int>(value.bits.size()) < width_hint)
        value.bits.insert(value.bits.begin(), width_hint - value.bits.size(), '0');
    if (static_cast<int>(value.bits.size()) > width_hint)
        value.bits = value.bits.substr(value.bits.size() - width_hint);
}

void finalize(LogicValue& value, const std::string& body_if_no_bits) {
    value.has_x = value.bits.find('x') != std::string::npos ||
                  body_if_no_bits.find('x') != std::string::npos;
    value.has_z = value.bits.find('z') != std::string::npos ||
                  body_if_no_bits.find('z') != std::string::npos;
    value.known = !value.has_x && !value.has_z;
    if (value.width_reliable && value.width <= 0 && !value.bits.empty())
        value.width = static_cast<int>(value.bits.size());

    std::string hex = value.bits.empty() ? clean_lower(body_if_no_bits) : bits_to_hex(value.bits);
    if (hex.empty()) hex = "0";
    value.display = value.width_reliable && value.width > 0
        ? std::to_string(value.width) + "'h" + hex
        : "'h" + hex;
}

LogicValue invalid_literal(const std::string& raw, const std::string& error) {
    LogicValue value;
    value.raw = raw;
    value.valid = false;
    value.known = false;
    value.error = error;
    return value;
}

LogicValue from_body(const std::string& raw, char radix, const std::string& body,
                     int width_hint, bool explicit_width) {
    LogicValue value;
    value.raw = raw;
    value.width = explicit_width ? width_hint : 0;
    value.width_reliable = explicit_width && width_hint > 0;
    char r = static_cast<char>(std::tolower(static_cast<unsigned char>(radix)));
    std::string clean = clean_lower(body);
    if (r == 'b') {
        value.bits = bin_to_bits(clean);
        if (!value.width_reliable) {
            value.width = static_cast<int>(value.bits.size());
            value.width_reliable = !value.bits.empty();
        }
    } else if (r == 'd') {
        if (clean.find_first_of("xz") != std::string::npos)
            return invalid_literal(raw, "decimal logic literal cannot contain x or z");
        value.bits = dec_to_bits(clean);
    } else {
        value.bits = hex_to_bits(clean);
    }
    if (value.bits.empty()) return invalid_literal(raw, "invalid logic value literal: " + raw);
    apply_width(value, width_hint);
    finalize(value, clean);
    return value;
}

} // namespace

bool is_legacy_0x_literal(const std::string& text) {
    std::string s = trim(text);
    return s.size() > 2 && s[0] == '0' && (s[1] == 'x' || s[1] == 'X');
}

std::string value_format_invalid_message(const std::string& value) {
    return "invalid value literal: " + value +
           "; 0x prefix is not accepted in xdebug JSON requests; use SystemVerilog literal such as 32'h22 or 'h22";
}

LogicValue logic_value_from_fsdb_raw(const std::string& raw, char radix, int width_hint) {
    std::string s = trim(raw);
    if (s.empty()) return invalid_literal(raw, "empty logic value");

    int explicit_width = 0;
    char r = radix ? radix : 'h';
    std::string body = s;
    size_t tick = s.find('\'');
    if (tick != std::string::npos && tick + 1 < s.size()) {
        if (tick > 0) explicit_width = std::atoi(s.substr(0, tick).c_str());
        r = s[tick + 1];
        body = s.substr(tick + 2);
    } else if (is_legacy_0x_literal(s)) {
        r = 'h';
        body = s.substr(2);
    } else if (s.size() > 2 && s[0] == '0' && (s[1] == 'b' || s[1] == 'B')) {
        r = 'b';
        body = s.substr(2);
    }
    int width = width_hint > 0 ? width_hint : explicit_width;
    return from_body(raw, r, body, width, width > 0);
}

LogicValue logic_value_from_bits(const std::string& bits, int width_hint) {
    LogicValue value;
    value.raw = bits;
    value.bits = bin_to_bits(bits);
    if (value.bits.empty()) return invalid_literal(bits, "invalid bit string");
    int width = width_hint > 0 ? width_hint : static_cast<int>(value.bits.size());
    apply_width(value, width);
    finalize(value, value.bits);
    return value;
}

LogicValue parse_user_logic_literal(const std::string& text) {
    std::string s = trim(text);
    if (s.empty()) return invalid_literal(text, "empty value literal");
    if (is_legacy_0x_literal(s)) return invalid_literal(text, value_format_invalid_message(text));

    size_t tick = s.find('\'');
    if (tick != std::string::npos && tick + 1 < s.size()) {
        int width = tick > 0 ? std::atoi(s.substr(0, tick).c_str()) : 0;
        char radix = s[tick + 1];
        std::string body = s.substr(tick + 2);
        return from_body(text, radix, body, width, width > 0);
    }

    if (!decimal_only(clean_lower(s)))
        return invalid_literal(text, "invalid value literal: " + text + "; use SystemVerilog literal such as 32'h22 or 'h22");
    return from_body(text, 'd', s, 0, false);
}

Json logic_value_json(const LogicValue& value) {
    Json out;
    out["value"] = logic_value_compact_string(value);
    out["known"] = value.known;
    if (value.width_reliable && value.width > 0) out["width"] = value.width;
    if (value.width_reliable && !value.bits.empty()) out["bits"] = value.bits;
    if (!value.known) {
        out["has_x"] = value.has_x;
        out["has_z"] = value.has_z;
    }
    return out;
}

std::string logic_value_compact_string(const LogicValue& value) {
    return value.display.empty() ? trim(value.raw) : value.display;
}

std::string logic_value_compare_key(const LogicValue& value) {
    if (!value.valid || !value.known) return std::string();
    std::string key = value.bits.empty() ? logic_value_compact_string(value) : bits_to_hex(value.bits);
    size_t first = key.find_first_not_of('0');
    return first == std::string::npos ? "0" : key.substr(first);
}

bool logic_value_has_xz(const LogicValue& value) {
    return !value.known || value.has_x || value.has_z;
}

} // namespace xdebug_waveform
