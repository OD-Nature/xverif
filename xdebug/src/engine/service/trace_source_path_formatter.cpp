#include "service/trace_source_path_formatter.h"

#include "api/text_response_builder.h"

#include "npi.h"
#include "npi_hdl.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <iomanip>
#include <set>
#include <sstream>

namespace xdebug_design {

namespace {

std::string scalar_text(const Json& object, const char* key) {
    if (!object.is_object() || !object.contains(key)) return std::string();
    const Json& value = object[key];
    if (!xdebug::is_xout_scalar_json(value)) return std::string();
    return xdebug::json_to_xout_value(value);
}

std::string trim_copy(const std::string& input) {
    size_t begin = 0;
    while (begin < input.size() && std::isspace(static_cast<unsigned char>(input[begin]))) ++begin;
    size_t end = input.size();
    while (end > begin && std::isspace(static_cast<unsigned char>(input[end - 1]))) --end;
    return input.substr(begin, end - begin);
}

bool looks_like_signal_name(const std::string& text) {
    if (text.empty() || text.find("npi") == 0) return false;
    size_t last_dot = text.rfind('.');
    if (last_dot != std::string::npos) {
        std::string tail = text.substr(last_dot + 1);
        if (tail == "if" || tail == "assign") return false;
    }
    bool has_dot = false;
    bool has_alpha = false;
    for (char ch : text) {
        unsigned char uch = static_cast<unsigned char>(ch);
        if (std::isalpha(uch) || ch == '_') has_alpha = true;
        if (ch == '.') has_dot = true;
        if (std::isalnum(uch) || ch == '_' || ch == '$' || ch == '.' ||
            ch == '[' || ch == ']' || ch == ':') {
            continue;
        }
        return false;
    }
    return has_alpha && has_dot;
}

std::string signal_name_from_text(std::string text) {
    text = trim_copy(text);
    if (looks_like_signal_name(text)) return text;
    size_t comma = text.find(',');
    if (comma != std::string::npos) text = trim_copy(text.substr(comma + 1));
    size_t cut = text.find_first_of(",;={ \t");
    if (cut != std::string::npos) text = trim_copy(text.substr(0, cut));
    return looks_like_signal_name(text) ? text : std::string();
}

int scalar_int(const Json& object, const char* key) {
    if (!object.is_object() || !object.contains(key)) return 0;
    const Json& value = object[key];
    if (value.is_number_integer()) return value.get<int>();
    if (value.is_number_unsigned()) return static_cast<int>(value.get<unsigned int>());
    if (value.is_string()) {
        try { return std::stoi(value.get<std::string>()); } catch (...) { return 0; }
    }
    return 0;
}

void append_unique(std::vector<std::string>& out, const std::string& value) {
    if (value.empty()) return;
    if (std::find(out.begin(), out.end(), value) == out.end()) out.push_back(value);
}

void append_signal(std::vector<std::string>& out, const std::string& value) {
    append_unique(out, signal_name_from_text(value));
}

Json strings_to_json(const std::vector<std::string>& values) {
    Json out = Json::array();
    for (const auto& value : values) out.push_back(value);
    return out;
}

std::vector<std::string> signal_path_from_edge(const Json& edge,
                                               const std::string& signal,
                                               const std::string& mode) {
    std::vector<std::string> path;
    std::string from = scalar_text(edge, "from");
    std::string to = scalar_text(edge, "to");
    if (mode == "load") {
        append_signal(path, from.empty() ? signal : from);
        append_signal(path, to);
    } else {
        append_signal(path, from);
        append_signal(path, to.empty() ? signal : to);
    }
    if (path.empty()) append_signal(path, signal);
    return path;
}

std::vector<std::string> signal_path_from_record(const Json& record,
                                                 const std::string& signal,
                                                 const std::string& mode) {
    std::vector<std::string> path;
    std::string related = scalar_text(record, "signal");
    if (mode == "load") {
        append_signal(path, signal);
        append_signal(path, related);
    } else {
        append_signal(path, related);
        append_signal(path, signal);
    }
    if (path.empty()) append_signal(path, signal);
    return path;
}

void add_path_if_valid(Json& paths,
                       std::set<std::string>& seen,
                       const std::string& file,
                       int line,
                       const std::vector<std::string>& signal_path) {
    if (file.empty() || line <= 0 || signal_path.empty()) return;
    std::ostringstream key;
    key << file << ":" << line;
    for (const auto& signal : signal_path) key << "|" << signal;
    if (!seen.insert(key.str()).second) return;
    Json item = make_source_path_item_from_location(file, line, signal_path);
    if (!item.empty()) paths.push_back(item);
}

Json source_lines_from_file(const std::string& file, int line, int context_lines) {
    Json context = Json::array();
    if (file.empty() || line <= 0) return context;
    std::ifstream in(file);
    if (!in) return context;
    std::vector<std::string> lines;
    std::string text;
    while (std::getline(in, text)) lines.push_back(text);
    if (line > static_cast<int>(lines.size())) return context;
    int begin = std::max(1, line - context_lines);
    int end = std::min(static_cast<int>(lines.size()), line + context_lines);
    for (int i = begin; i <= end; ++i) {
        context.push_back({{"line", i}, {"text", lines[i - 1]}, {"active", i == line}});
    }
    return context;
}

void emit_source_item_xout(std::string& text,
                           const Json& item,
                           const std::string& heading,
                           bool include_heading) {
    if (!item.is_object()) return;
    if (include_heading) {
        text += heading + ":\n";
    }
    const std::string file = scalar_text(item, "file");
    const int line = scalar_int(item, "line");
    if (!file.empty() && line > 0) {
        text += "source: " + file + ":" + std::to_string(line) + "\n";
    }
    const Json context = item.value("source_context", Json::array());
    if (context.is_array()) {
        for (const auto& row : context) {
            if (!row.is_object()) continue;
            int row_line = scalar_int(row, "line");
            bool active = row.value("active", false);
            std::ostringstream prefix;
            prefix << (active ? ">" : " ") << std::setw(4) << row_line << " | ";
            text += prefix.str() + row.value("text", std::string()) + "\n";
        }
    }
    const Json signal_path = item.value("signal_path", Json::array());
    std::ostringstream path;
    if (signal_path.is_array()) {
        for (size_t i = 0; i < signal_path.size(); ++i) {
            if (!signal_path[i].is_string()) continue;
            if (path.tellp() > 0) path << " -> ";
            path << signal_path[i].get<std::string>();
        }
    }
    if (path.tellp() > 0) text += "signal_path: " + path.str() + "\n";
}

} // namespace

Json source_window_from_location(const std::string& file, int line, int context_lines) {
    return source_lines_from_file(file, line, std::max(0, context_lines));
}

Json source_window_from_npi_handle(npiHandle handle, int context_lines) {
    if (!handle) return Json::array();
    int line = npi_get(npiLineNo, handle);
    const char* raw_file = npi_get_str(npiFile, handle);
    return source_window_from_location(raw_file ? raw_file : "", line, context_lines);
}

Json make_source_path_item_from_location(const std::string& file,
                                         int line,
                                         const std::vector<std::string>& signal_path,
                                         int context_lines) {
    Json context = source_window_from_location(file, line, context_lines);
    if (context.empty()) return Json::object();
    Json item;
    item["file"] = file;
    item["line"] = line;
    item["source_context"] = context;
    item["signal_path"] = strings_to_json(signal_path);
    return item;
}

Json make_source_path_item_from_npi_handle(npiHandle handle,
                                           const std::vector<std::string>& signal_path,
                                           int context_lines) {
    if (!handle) return Json::object();
    int line = npi_get(npiLineNo, handle);
    const char* raw_file = npi_get_str(npiFile, handle);
    return make_source_path_item_from_location(raw_file ? raw_file : "",
                                               line,
                                               signal_path,
                                               context_lines);
}

Json simplify_trace_driver_load_payload(const Json& raw,
                                        const std::string& action,
                                        const std::string& signal,
                                        const std::string& mode) {
    Json paths = Json::array();
    std::set<std::string> seen;
    Json edges = raw.value("dependency_edges", Json::array());
    if (edges.is_array()) {
        for (const auto& edge : edges) {
            add_path_if_valid(paths, seen, scalar_text(edge, "file"), scalar_int(edge, "line"),
                              signal_path_from_edge(edge, signal, mode));
        }
    }
    Json results = raw.value("results", Json::array());
    if (results.is_array()) {
        for (const auto& record : results) {
            add_path_if_valid(paths, seen, scalar_text(record, "file"), scalar_int(record, "line"),
                              signal_path_from_record(record, signal, mode));
        }
    }

    Json out;
    out["summary"] = {
        {"signal", signal},
        {"mode", mode},
        {"path_count", static_cast<int>(paths.size())},
        {"truncated", raw.value("truncated", false)}
    };
    out["paths"] = paths;
    out["truncated"] = raw.value("truncated", false);
    (void)action;
    return out;
}

Json simplify_active_driver_payload(const Json& raw,
                                    const std::string& signal,
                                    const std::string& requested_time) {
    Json paths = Json::array();
    std::set<std::string> seen;
    std::string active_time = raw.value("summary", Json::object()).value("active_time", std::string());
    Json trace_nodes = raw.value("trace", Json::object()).value("nodes", Json::array());
    if (trace_nodes.is_array()) {
        for (const auto& node : trace_nodes) {
            std::vector<std::string> path;
            Json signals = node.value("signals", Json::array());
            if (signals.is_array()) {
                for (const auto& item : signals) {
                    if (item.is_string()) append_signal(path, item.get<std::string>());
                }
            }
            append_signal(path, scalar_text(node, "next_signal"));
            append_signal(path, scalar_text(node, "signal"));
            if (active_time.empty()) active_time = scalar_text(node, "active_time");
            add_path_if_valid(paths, seen, scalar_text(node, "file"), scalar_int(node, "line"), path);
        }
    }
    if (paths.empty()) {
        Json driver = raw.value("driver", Json::object());
        if (driver.is_object()) {
            std::vector<std::string> path;
            Json signals = driver.value("signals", Json::array());
            if (signals.is_array()) {
                for (const auto& item : signals) {
                    if (item.is_string()) append_signal(path, item.get<std::string>());
                }
            }
            append_signal(path, signal);
            add_path_if_valid(paths, seen, scalar_text(driver, "file"), scalar_int(driver, "line"), path);
        }
    }

    Json out;
    out["summary"] = {
        {"signal", signal},
        {"requested_time", requested_time},
        {"active_time", active_time},
        {"path_count", static_cast<int>(paths.size())},
        {"truncated", raw.value("truncated", false)}
    };
    out["paths"] = paths;
    out["truncated"] = raw.value("truncated", false);
    return out;
}

Json simplify_active_driver_chain_payload(const Json& raw,
                                          const std::string& signal,
                                          const std::string& start_time) {
    Json hops = Json::array();
    Json chain_object = raw.value("chain", Json::object());
    Json chain = chain_object.is_object() ? chain_object.value("chain", Json::array()) : Json::array();
    if (chain.is_array()) {
        std::set<std::string> seen;
        for (const auto& node : chain) {
            std::vector<std::string> path;
            append_signal(path, scalar_text(node, "next"));
            append_signal(path, scalar_text(node, "signal"));
            std::string file = scalar_text(node, "file");
            int line = scalar_int(node, "line");
            if (file.empty() || line <= 0 || path.empty()) continue;
            std::ostringstream key;
            key << node.value("index", 0) << "|" << file << ":" << line;
            for (const auto& item : path) key << "|" << item;
            if (!seen.insert(key.str()).second) continue;
            Json hop = make_source_path_item_from_location(file, line, path);
            if (hop.empty()) continue;
            hop["index"] = node.value("index", static_cast<int>(hops.size()));
            hops.push_back(hop);
        }
    }

    Json summary = raw.value("summary", Json::object());
    Json out;
    out["summary"] = {
        {"signal", signal},
        {"start_time", start_time},
        {"hop_count", static_cast<int>(hops.size())},
        {"termination", summary.value("termination", raw.value("termination", std::string("unresolved")))},
        {"truncated", raw.value("truncated", false)}
    };
    out["hops"] = hops;
    out["truncated"] = raw.value("truncated", false);
    return out;
}

std::string render_source_path_xout(const std::string& action, const Json& response) {
    xdebug::TextResponseBuilder out("xdebug");
    out.emit_header(action);
    Json summary = response.value("summary", Json::object());
    if (summary.is_object() && !summary.empty()) {
        out.emit_section("summary");
        for (auto it = summary.begin(); it != summary.end(); ++it) {
            if (xdebug::is_xout_scalar_json(it.value())) out.emit_kv(it.key(), it.value());
        }
    }
    std::string text = out.str();
    const Json data = response.value("data", Json::object());
    const Json paths = data.value("paths", Json::array());
    if (paths.is_array()) {
        for (const auto& item : paths) {
            if (!text.empty() && text.back() != '\n') text.push_back('\n');
            if (!text.empty()) text.push_back('\n');
            emit_source_item_xout(text, item, "", false);
        }
    }
    const Json hops = data.value("hops", Json::array());
    if (hops.is_array()) {
        for (const auto& item : hops) {
            if (!text.empty() && text.back() != '\n') text.push_back('\n');
            if (!text.empty()) text.push_back('\n');
            int index = item.value("index", 0);
            emit_source_item_xout(text, item, "hop " + std::to_string(index), true);
        }
    }
    while (!text.empty() && text.back() == '\n') text.pop_back();
    text.push_back('\n');
    return text;
}

} // namespace xdebug_design
