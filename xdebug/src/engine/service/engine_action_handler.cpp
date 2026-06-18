#include "engine_action_handler.h"

#include "../../api/text_response_builder.h"

#include <set>
#include <vector>

namespace xdebug_design {

// Helper: recursively render a JSON value.
static void render_data_value(xdebug::TextResponseBuilder& out,
                              const std::string& key, const Json& val) {
    if (val.is_string() || val.is_number() || val.is_boolean()) {
        out.emit_kv(key, val);
    } else if (val.is_array() && val.empty()) {
        out.emit_kv(key, "[empty]");
    } else if (val.is_array() && val.size() > 0 &&
               (val[0].is_string() || val[0].is_number() || val[0].is_boolean())) {
        out.emit_section(key);
        int n = std::min(20, (int)val.size());
        for (int i = 0; i < n; ++i)
            out.emit_row({xdebug::json_to_xout_value(val[i])});
        if ((int)val.size() > n)
            out.emit_kv("(+ " + std::to_string(val.size() - n) + " more)", "");
    } else if (val.is_array() && val.size() > 0 && val[0].is_object()) {
        int count = (int)val.size();
        out.emit_section(key);

        // Collect top-level scalar keys + flatten one level of object keys
        std::vector<std::string> keys;
        std::set<std::string> seen;
        for (int i = 0; i < std::min(5, count); ++i) {
            for (auto ki = val[i].begin(); ki != val[i].end(); ++ki) {
                if (ki.value().is_string() || ki.value().is_number() ||
                    ki.value().is_boolean()) {
                    if (seen.insert(ki.key()).second) keys.push_back(ki.key());
                } else if (ki.value().is_object()) {
                    for (auto oi = ki.value().begin(); oi != ki.value().end(); ++oi) {
                        std::string fkey = ki.key() + "." + oi.key();
                        if ((oi.value().is_string() || oi.value().is_number()) &&
                            seen.insert(fkey).second) keys.push_back(fkey);
                    }
                }
            }
        }

        out.emit_row(keys);  // header
        int n = std::min(20, count);
        for (int i = 0; i < n; ++i) {
            std::vector<std::string> row;
            for (const auto& k : keys) {
                auto dot = k.find('.');
                if (dot != std::string::npos) {
                    // Walk nested path safely: "parent.child" -> obj["parent"]["child"]
                    const Json* node = &val[i];
                    std::string remain = k;
                    while (node != nullptr && node->is_object()) {
                        auto d = remain.find('.');
                        std::string seg = remain.substr(0, d);
                        if (d == std::string::npos) {
                            row.push_back(xdebug::json_to_xout_value(
                                node->value(seg, Json())));
                            node = nullptr;  // done
                        } else {
                            auto it = node->find(seg);
                            node = (it != node->end()) ? &(*it) : nullptr;
                            remain = remain.substr(d + 1);
                        }
                    }
                    if (node != nullptr) row.push_back("");  // unresolvable
                } else {
                    row.push_back(xdebug::json_to_xout_value(
                        val[i].value(k, Json())));
                }
            }
            out.emit_row(row);
        }
        if (count > n)
            out.emit_kv("(+ " + std::to_string(count - n) + " more)", "");
    } else if (val.is_object()) {
        out.emit_section(key);
        for (auto it = val.begin(); it != val.end(); ++it)
            render_data_value(out, it.key(), it.value());
    }
}

std::string EngineActionHandler::render_xout(const Json& response) const {
    xdebug::TextResponseBuilder out("xdebug");
    out.emit_header(action_name());

    // ── summary ──
    if (response.contains("summary") && response["summary"].is_object()) {
        out.emit_section("summary");
        for (auto it = response["summary"].begin();
             it != response["summary"].end(); ++it) {
            if (it.value().is_string() || it.value().is_number() ||
                it.value().is_boolean()) {
                out.emit_kv(it.key(), it.value());
            }
        }
    }

    // ── data ── recursive tree
    const Json& data = response.value("data", Json::object());
    if (data.is_object() && !data.empty()) {
        out.emit_section("data");
        for (auto it = data.begin(); it != data.end(); ++it) {
            if (it.key() == "summary") continue;  // already rendered above
            render_data_value(out, it.key(), it.value());
        }
    }

    // ── findings ──
    if (response.contains("findings") && response["findings"].is_array() &&
        !response["findings"].empty()) {
        out.emit_section("findings");
        for (const auto& f : response["findings"])
            out.emit_row({xdebug::json_to_xout_value(f)});
    }

    return out.str();
}

} // namespace xdebug_design
