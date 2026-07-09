#include "api/text_response_builder.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <iomanip>
#include <set>

namespace xdebug {

namespace {

constexpr size_t kMaxValueLength = 4096;

bool is_empty_json(const Json& value) {
    return value.is_null() ||
           (value.is_array() && value.empty()) ||
           (value.is_object() && value.empty());
}

std::string trim_copy(const std::string& input) {
    size_t begin = 0;
    while (begin < input.size() &&
           std::isspace(static_cast<unsigned char>(input[begin]))) {
        ++begin;
    }
    size_t end = input.size();
    while (end > begin &&
           std::isspace(static_cast<unsigned char>(input[end - 1]))) {
        --end;
    }
    return input.substr(begin, end - begin);
}

std::string lower_no_underscores(std::string text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        if (c == '_' || std::isspace(static_cast<unsigned char>(c))) continue;
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

bool contains_xz_text(const std::string& text) {
    std::string s = trim_copy(text);
    size_t start = 0;
    if (s.size() >= 2 && s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
        start = 2;
    } else if (s.size() >= 2 && s[0] == '\'' &&
               (s[1] == 'h' || s[1] == 'H' || s[1] == 'b' || s[1] == 'B' ||
                s[1] == 'd' || s[1] == 'D')) {
        start = 2;
    }
    return s.find_first_of("xXzZ", start) != std::string::npos;
}

bool is_value_object(const Json& value) {
    if (!value.is_object() || !value.contains("value")) return false;
    const Json& raw = value["value"];
    if (!(raw.is_string() || raw.is_number() || raw.is_boolean() || raw.is_null())) return false;
    return value.contains("known") || value.contains("bits") || value.contains("width");
}

std::string strip_value_prefix(const std::string& text, char& base) {
    std::string s = trim_copy(text);
    base = 0;
    size_t tick = s.find('\'');
    if (tick != std::string::npos && tick + 1 < s.size()) {
        base = static_cast<char>(std::tolower(static_cast<unsigned char>(s[tick + 1])));
        return s.substr(tick + 2);
    }
    if (s.size() > 2 && s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
        base = 'h';
        return s.substr(2);
    }
    if (s.size() > 2 && s[0] == '0' && (s[1] == 'b' || s[1] == 'B')) {
        base = 'b';
        return s.substr(2);
    }
    base = 'h';
    return s;
}

std::string bits_to_hex(std::string bits) {
    bits = lower_no_underscores(bits);
    if (bits.empty()) return "0";
    size_t pad = (4 - bits.size() % 4) % 4;
    bits.insert(bits.begin(), pad, '0');
    static const char* hex = "0123456789abcdef";
    std::string out;
    for (size_t i = 0; i < bits.size(); i += 4) {
        bool has_x = false;
        bool has_z = false;
        int v = 0;
        for (size_t j = 0; j < 4; ++j) {
            char c = bits[i + j];
            if (c == 'x') has_x = true;
            else if (c == 'z') has_z = true;
            else if (c != '0' && c != '1') has_x = true;
            v = (v << 1) | (c == '1' ? 1 : 0);
        }
        out.push_back(has_x ? 'x' : (has_z ? 'z' : hex[v]));
    }
    return out.empty() ? "0" : out;
}

std::string bin_to_hex(std::string bits) {
    return bits_to_hex(std::move(bits));
}

std::string dec_to_hex(const std::string& text) {
    std::string clean = lower_no_underscores(text);
    if (clean.empty() || contains_xz_text(clean)) return clean;
    char* end = nullptr;
    unsigned long long v = std::strtoull(clean.c_str(), &end, 10);
    if (!end || *end != '\0') return clean;
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%llx", v);
    return buf;
}

std::string value_json_text(const Json& value) {
    if (value.is_null()) return "";
    if (value.is_string()) return value.get<std::string>();
    if (value.is_boolean()) return value.get<bool>() ? "1" : "0";
    if (value.is_number_integer()) return std::to_string(value.get<long long>());
    if (value.is_number_unsigned()) return std::to_string(value.get<unsigned long long>());
    if (value.is_number_float()) return value.dump();
    return value.dump();
}

std::string compact_value_object(const Json& value) {
    std::string raw = trim_copy(value_json_text(value.value("value", Json())));
    std::string bits = value.value("bits", std::string());
    int width = value.value("width", 0);
    const bool known = value.value("known", !contains_xz_text(raw) && !contains_xz_text(bits));

    std::string hex_text;
    int inferred_width = width;
    if (!bits.empty()) {
        std::string clean_bits = lower_no_underscores(bits);
        if (inferred_width <= 0) inferred_width = static_cast<int>(clean_bits.size());
        hex_text = bits_to_hex(clean_bits);
    } else {
        char base = 0;
        std::string body = strip_value_prefix(raw, base);
        body = lower_no_underscores(body);
        if (base == 'b') {
            if (inferred_width <= 0) inferred_width = static_cast<int>(body.size());
            hex_text = bin_to_hex(body);
            bits = body;
        } else if (base == 'd') {
            hex_text = dec_to_hex(body);
        } else {
            hex_text = body.empty() ? "0" : body;
        }
    }

    if (hex_text.empty()) hex_text = "0";
    std::string out = inferred_width > 0
        ? std::to_string(inferred_width) + "'h" + hex_text
        : "'h" + hex_text;

    if (!known || contains_xz_text(raw) || contains_xz_text(bits) || contains_xz_text(hex_text)) {
        out += " known=false";
        if (!bits.empty()) out += " bits=" + lower_no_underscores(bits);
        if (inferred_width > 0) out += " width=" + std::to_string(inferred_width);
    }
    return out;
}

bool is_field_map(const Json& value) {
    if (!value.is_object() || value.empty() || is_value_object(value)) return false;
    for (auto it = value.begin(); it != value.end(); ++it) {
        if (!is_value_object(it.value())) return false;
    }
    return true;
}

std::string compact_field_map(const Json& value) {
    std::string out;
    if (!value.is_object()) return out;
    for (auto it = value.begin(); it != value.end(); ++it) {
        std::string cell = sanitize_xout_key(it.key()) + "=" + compact_value_object(it.value());
        if (!out.empty()) out.push_back(' ');
        out += cell;
    }
    return out;
}

std::string collapse_row_column(const std::string& input) {
    std::string out;
    bool in_space = false;
    for (char ch : input) {
        unsigned char uch = static_cast<unsigned char>(ch);
        if (std::isspace(uch)) {
            if (!in_space && !out.empty()) out.push_back(' ');
            in_space = true;
        } else {
            out.push_back(ch);
            in_space = false;
        }
    }
    if (!out.empty() && out.back() == ' ') out.pop_back();
    return out;
}

struct TableColumn {
    std::string label;
    std::string parent;
    std::string key;
};

void collect_table_columns_from_item(const Json& item,
                                     std::vector<TableColumn>& columns,
                                     std::set<std::string>& seen) {
    if (!item.is_object()) return;
    for (auto it = item.begin(); it != item.end(); ++it) {
        if (is_xout_scalar_json(it.value())) {
            std::string label = sanitize_xout_key(it.key());
            if (seen.insert(label).second) columns.push_back({label, std::string(), it.key()});
        } else if (it.value().is_object()) {
            for (auto child = it.value().begin(); child != it.value().end(); ++child) {
                if (!is_xout_scalar_json(child.value())) continue;
                std::string label = it.key() == "signals"
                    ? sanitize_xout_key(child.key())
                    : sanitize_xout_key(it.key() + "." + child.key());
                if (seen.insert(label).second) columns.push_back({label, it.key(), child.key()});
            }
        }
    }
}

std::string table_cell_value(const Json& item, const TableColumn& column) {
    if (!item.is_object()) return std::string();
    if (column.parent.empty()) {
        auto it = item.find(column.key);
        if (it == item.end()) return std::string();
        return json_to_xout_value(*it);
    }
    auto parent = item.find(column.parent);
    if (parent == item.end() || !parent->is_object()) return std::string();
    auto child = parent->find(column.key);
    if (child == parent->end()) return std::string();
    return json_to_xout_value(*child);
}

} // namespace

TextResponseBuilder::TextResponseBuilder(std::string tool) : tool_(std::move(tool)) {}

void TextResponseBuilder::emit_header(const std::string& action) {
    if (wrote_header_) return;
    out_ << "@" << tool_ << "." << action << ".v1\n";
    wrote_header_ = true;
}

void TextResponseBuilder::emit_section(const std::string& name) {
    flush_kv_block();
    pending_section_ = sanitize_xout_key(name);
}

void TextResponseBuilder::emit_kv(const std::string& key, const Json& value) {
    if (is_empty_json(value)) return;
    const std::string text = json_to_xout_value(value);
    if (text.empty()) return;
    const bool nested = in_section_ || !pending_section_.empty();
    ensure_section();
    pending_kv_.push_back({std::string(nested ? "  " : ""), sanitize_xout_key(key), text});
}

void TextResponseBuilder::emit_kv(const std::string& key, const std::string& value) {
    if (value.empty()) return;
    const bool nested = in_section_ || !pending_section_.empty();
    ensure_section();
    pending_kv_.push_back({std::string(nested ? "  " : ""),
                           sanitize_xout_key(key),
                           sanitize_xout_value(value)});
}

void TextResponseBuilder::emit_kv(const std::string& key, const char* value) {
    if (value == nullptr) return;
    emit_kv(key, std::string(value));
}

void TextResponseBuilder::emit_kv(const std::string& key, bool value) {
    emit_kv(key, std::string(value ? "true" : "false"));
}

void TextResponseBuilder::emit_kv(const std::string& key, int value) {
    emit_kv(key, std::to_string(value));
}

void TextResponseBuilder::emit_kv(const std::string& key, long long value) {
    emit_kv(key, std::to_string(value));
}

void TextResponseBuilder::emit_row(std::initializer_list<std::string> columns) {
    emit_row(std::vector<std::string>(columns.begin(), columns.end()));
}

void TextResponseBuilder::emit_row(const std::vector<std::string>& columns) {
    flush_kv_block();
    std::string row;
    for (const auto& col : columns) {
        std::string text = collapse_row_column(sanitize_xout_value(col));
        if (text.empty()) continue;
        if (!row.empty()) row.push_back(' ');
        row += text;
    }
    if (row.empty()) return;
    const bool nested = in_section_ || !pending_section_.empty();
    ensure_section();
    write_line(std::string(nested ? "  " : "") + row);
}

void TextResponseBuilder::emit_table(const std::vector<std::string>& columns,
                                     const std::vector<std::vector<std::string>>& rows) {
    flush_kv_block();
    if (columns.empty()) return;
    std::vector<size_t> widths(columns.size(), 0);
    std::vector<std::string> safe_columns;
    safe_columns.reserve(columns.size());
    for (size_t i = 0; i < columns.size(); ++i) {
        safe_columns.push_back(collapse_row_column(sanitize_xout_key(columns[i])));
        widths[i] = safe_columns.back().size();
    }

    std::vector<std::vector<std::string>> safe_rows;
    safe_rows.reserve(rows.size());
    for (const auto& row : rows) {
        std::vector<std::string> safe_row;
        safe_row.reserve(columns.size());
        for (size_t i = 0; i < columns.size(); ++i) {
            std::string cell;
            if (i < row.size()) cell = collapse_row_column(sanitize_xout_value(row[i]));
            widths[i] = std::max(widths[i], cell.size());
            safe_row.push_back(cell);
        }
        safe_rows.push_back(std::move(safe_row));
    }

    auto emit_cells = [&](const std::vector<std::string>& cells) {
        std::string line;
        for (size_t i = 0; i < columns.size(); ++i) {
            if (i) line += "  ";
            std::string cell = i < cells.size() ? cells[i] : std::string();
            line += cell;
            if (i + 1 < columns.size() && cell.size() < widths[i])
                line.append(widths[i] - cell.size(), ' ');
        }
        while (!line.empty() && line.back() == ' ') line.pop_back();
        const bool nested = in_section_ || !pending_section_.empty();
        ensure_section();
        write_line(std::string(nested ? "  " : "") + line);
    };

    emit_cells(safe_columns);
    for (const auto& row : safe_rows) emit_cells(row);
}

void TextResponseBuilder::emit_json_table(const Json& items, int max_rows) {
    flush_kv_block();
    if (!items.is_array() || items.empty()) return;
    std::vector<TableColumn> columns;
    std::set<std::string> seen;
    int count = std::min(max_rows, static_cast<int>(items.size()));
    for (int i = 0; i < count; ++i)
        collect_table_columns_from_item(items[i], columns, seen);
    if (columns.empty()) return;

    std::vector<std::string> headers;
    headers.reserve(columns.size());
    for (const auto& column : columns) headers.push_back(column.label);

    std::vector<std::vector<std::string>> rows;
    rows.reserve(count);
    for (int i = 0; i < count; ++i) {
        std::vector<std::string> row;
        row.reserve(columns.size());
        for (const auto& column : columns)
            row.push_back(table_cell_value(items[i], column));
        rows.push_back(std::move(row));
    }
    emit_table(headers, rows);
}

void TextResponseBuilder::emit_warning(const std::string& code, const std::string& message) {
    emit_section("warnings");
    emit_table({"code", "message"}, {{code, message}});
}

void TextResponseBuilder::emit_raw(const std::string& text) {
    flush_kv_block();
    wrote_content_ = true;
    out_ << text;
}

void TextResponseBuilder::emit_error(const Json& error) {
    if (!error.is_object()) return;
    if (error.contains("code")) emit_kv("code", error["code"]);
    if (error.contains("message")) emit_kv("message", error["message"]);
    if (error.contains("recoverable")) emit_kv("recoverable", error["recoverable"]);
    if (error.contains("error_layer")) emit_kv("error_layer", error["error_layer"]);
    if (error.contains("invalid_arg")) emit_kv("invalid_arg", error["invalid_arg"]);
    if (error.contains("expected")) emit_kv("expected", error["expected"]);
    if (error.contains("received")) emit_kv("received", error["received"]);
    if (error.contains("received_type")) emit_kv("received_type", error["received_type"]);
    if (error.contains("allowed_values")) emit_kv("allowed_values", error["allowed_values"]);
    if (error.contains("available_values")) emit_kv("available_values", error["available_values"]);
    if (error.contains("missing_name")) emit_kv("missing_name", error["missing_name"]);
    if (error.contains("missing_resource")) emit_kv("missing_resource", error["missing_resource"]);
    if (error.contains("required_any_of")) emit_kv("required_any_of", error["required_any_of"]);
    if (error.contains("did_you_mean")) emit_kv("did_you_mean", error["did_you_mean"]);
    if (error.contains("cause_code")) emit_kv("cause_code", error["cause_code"]);
    if (error.contains("example_note")) emit_kv("example_note", error["example_note"]);
    if (error.contains("correct_example")) {
        emit_section("correct_example");
        emit_kv("json", error["correct_example"]);
    }
    if (error.contains("next_actions") && error["next_actions"].is_array()) {
        emit_section("next_actions");
        for (const auto& action : error["next_actions"]) emit_row({json_to_xout_value(action)});
    }
}

std::string TextResponseBuilder::str() {
    flush_kv_block();
    std::string text = out_.str();
    while (!text.empty() && text.back() == '\n') text.pop_back();
    text.push_back('\n');
    return text;
}

void TextResponseBuilder::flush_kv_block() {
    if (pending_kv_.empty()) return;
    for (const auto& item : pending_kv_) {
        write_line(item.indent + item.key + ": " + item.value);
    }
    pending_kv_.clear();
}

void TextResponseBuilder::ensure_section() {
    if (pending_section_.empty()) return;
    if (wrote_content_) out_ << "\n";
    out_ << pending_section_ << ":\n";
    wrote_content_ = true;
    pending_section_.clear();
    in_section_ = true;
}

void TextResponseBuilder::write_line(const std::string& text) {
    if (!wrote_content_ && pending_section_.empty()) {
        if (wrote_header_) out_ << "\n";
        wrote_content_ = true;
        in_section_ = false;
    }
    out_ << text << "\n";
}

std::string sanitize_xout_key(const std::string& key) {
    std::string out;
    for (char ch : key) {
        unsigned char uch = static_cast<unsigned char>(ch);
        if (std::isalnum(uch) || ch == '_' || ch == '-' || ch == '.') {
            out.push_back(ch);
        } else {
            out.push_back('_');
        }
    }
    return out.empty() ? "field" : out;
}

std::string sanitize_xout_value(const std::string& value) {
    std::string out;
    out.reserve(std::min(value.size(), kMaxValueLength));
    for (char ch : value) {
        if (ch == '\n') {
            out += "\\n";
        } else if (ch == '\r') {
            out += "\\r";
        } else if (ch == '\t') {
            out.push_back(' ');
        } else {
            out.push_back(ch);
        }
        if (out.size() >= kMaxValueLength) {
            out += "...";
            break;
        }
    }
    return out;
}

std::string json_to_xout_value(const Json& value) {
    if (value.is_null()) return std::string();
    if (is_value_object(value)) return sanitize_xout_value(compact_value_object(value));
    if (is_field_map(value)) return sanitize_xout_value(compact_field_map(value));
    if (value.is_string()) return sanitize_xout_value(value.get<std::string>());
    if (value.is_boolean()) return value.get<bool>() ? "true" : "false";
    if (value.is_number_integer()) return std::to_string(value.get<long long>());
    if (value.is_number_unsigned()) return std::to_string(value.get<unsigned long long>());
    if (value.is_number_float()) return sanitize_xout_value(value.dump());
    return sanitize_xout_value(value.dump());
}

bool is_xout_scalar_json(const Json& value) {
    return value.is_string() || value.is_number() || value.is_boolean() ||
           is_value_object(value) || is_field_map(value);
}

bool is_xout_field_map_json(const Json& value) {
    return is_field_map(value);
}

} // namespace xdebug
