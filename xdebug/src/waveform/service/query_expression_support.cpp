#include "action_support.h"
#include "../protocol/protocol.h"
#include "../value/logic_value.h"

#include <cctype>

namespace xdebug_waveform {

bool query_value(const std::string& session_id,
                 const std::string& signal,
                 const std::string& time,
                 char fmt,
                 std::string& raw,
                 std::string& err) {
    std::string cmd = std::string(CMD_VALUE) + " " + signal + " " + time + " " + fmt;
    return capture_server_text(session_id, cmd, raw, err);
}

Json resolve_time_spec_json(const std::string& session_id,
                            const std::string& spec,
                            bool allow_max,
                            std::string& err) {
    Json out;
    if (spec.empty()) return out;
    std::string cmd = std::string(CMD_TIME_RESOLVE) + " " + spec + (allow_max ? " allow_max" : "");
    if (!capture_server_json(session_id, cmd, out, err)) return Json();
    return out;
}

bool build_range_specs(const Json& args,
                       std::string& begin,
                       std::string& end,
                       bool& around_window,
                       std::string& err) {
    Json tr = args.value("time_range", Json::object());
    begin = string_or(tr, "begin", string_or(args, "begin", ""));
    end = string_or(tr, "end", string_or(args, "end", ""));
    around_window = false;
    if (!begin.empty() || !end.empty()) {
        if (begin.empty()) begin = "0ns";
        if (end.empty()) end = "max";
        return true;
    }
    std::string around = string_or(args, "around", "");
    if (around.empty()) {
        begin = "0ns";
        end = "max";
        return true;
    }
    std::string before = string_or(args, "before", "0ns");
    std::string after = string_or(args, "after", "0ns");
    if (before.empty()) before = "0ns";
    if (after.empty()) after = "0ns";
    if (!before.empty() && before[0] == '@') {
        err = "TIME_SPEC_INVALID: before must be a duration, not a TimeSpec";
        return false;
    }
    if (!after.empty() && after[0] == '@') {
        err = "TIME_SPEC_INVALID: after must be a duration, not a TimeSpec";
        return false;
    }
    begin = around + "-" + before;
    end = around + "+" + after;
    around_window = true;
    return true;
}

void fill_resolved_range(Json& out,
                         const std::string& sid,
                         const std::string& begin,
                         const std::string& end,
                         bool around_window,
                         std::string& err) {
    if (!out["data"].is_object()) out["data"] = Json::object();
    out["data"]["resolved_time_range"]["begin"] = resolve_time_spec_json(sid, begin, false, err);
    out["data"]["resolved_time_range"]["end"] = resolve_time_spec_json(sid, end, true, err);
    if (around_window) out["data"]["resolved_time_range"]["source"] = "around_window";
}

namespace {

Tri tri_not(Tri v) {
    if (v == Tri::Unknown) return Tri::Unknown;
    return v == Tri::True ? Tri::False : Tri::True;
}

Tri tri_and(Tri a, Tri b) {
    if (a == Tri::False || b == Tri::False) return Tri::False;
    if (a == Tri::Unknown || b == Tri::Unknown) return Tri::Unknown;
    return Tri::True;
}

Tri tri_or(Tri a, Tri b) {
    if (a == Tri::True || b == Tri::True) return Tri::True;
    if (a == Tri::Unknown || b == Tri::Unknown) return Tri::Unknown;
    return Tri::False;
}

Tri value_to_bool(const std::string& raw) {
    LogicValue value = logic_value_from_fsdb_raw(raw, 'h');
    if (logic_value_has_xz(value)) return Tri::Unknown;
    return logic_value_compare_key(value) == "0" ? Tri::False : Tri::True;
}

class ExprParser {
public:
    ExprParser(const std::string& text, const Json& values)
        : text_(text), values_(values), pos_(0), ok_(true) {}

    Tri parse() {
        Tri v = parse_or();
        skip_ws();
        if (pos_ != text_.size()) ok_ = false;
        return ok_ ? v : Tri::Unknown;
    }

    bool ok() const { return ok_; }

private:
    void skip_ws() {
        while (pos_ < text_.size() && std::isspace(static_cast<unsigned char>(text_[pos_]))) ++pos_;
    }

    bool eat(const std::string& token) {
        skip_ws();
        if (text_.compare(pos_, token.size(), token) == 0) {
            pos_ += token.size();
            return true;
        }
        return false;
    }

    std::string ident() {
        skip_ws();
        size_t start = pos_;
        if (pos_ < text_.size() &&
            (std::isalpha(static_cast<unsigned char>(text_[pos_])) || text_[pos_] == '_')) {
            ++pos_;
            while (pos_ < text_.size() &&
                   (std::isalnum(static_cast<unsigned char>(text_[pos_])) ||
                    text_[pos_] == '_' || text_[pos_] == '.')) {
                ++pos_;
            }
        }
        return text_.substr(start, pos_ - start);
    }

    std::string literal() {
        skip_ws();
        size_t start = pos_;
        if (pos_ < text_.size() && text_[pos_] == '\'') {
            ++pos_;
            if (pos_ < text_.size()) ++pos_;
            while (pos_ < text_.size() && std::isxdigit(static_cast<unsigned char>(text_[pos_]))) ++pos_;
            return text_.substr(start, pos_ - start);
        }
        while (pos_ < text_.size() &&
               (std::isalnum(static_cast<unsigned char>(text_[pos_])) || text_[pos_] == 'x' ||
                text_[pos_] == 'X' || text_[pos_] == '_' || text_[pos_] == '\'')) {
            ++pos_;
        }
        return text_.substr(start, pos_ - start);
    }

    std::string value_for(const std::string& name) {
        auto it = values_.find(name);
        if (it == values_.end() || !it->is_object() || !it->contains("value")) {
            ok_ = false;
            return "";
        }
        return (*it)["value"]["value"].get<std::string>();
    }

    Tri parse_primary() {
        if (eat("(")) {
            Tri v = parse_or();
            if (!eat(")")) ok_ = false;
            return v;
        }
        if (eat("!")) return tri_not(parse_primary());

        std::string name = ident();
        if (name.empty()) {
            ok_ = false;
            return Tri::Unknown;
        }
        bool neq = false;
        if (eat("==") || (neq = eat("!="))) {
            std::string rhs = literal();
            if (rhs.empty()) {
                ok_ = false;
                return Tri::Unknown;
            }
            std::string lhs_val = value_for(name);
            LogicValue lhs = logic_value_from_fsdb_raw(lhs_val, 'h');
            LogicValue rhs_value = parse_user_logic_literal(rhs);
            if (!rhs_value.valid) {
                ok_ = false;
                return Tri::Unknown;
            }
            if (logic_value_has_xz(lhs) || logic_value_has_xz(rhs_value)) return Tri::Unknown;
            bool eq = logic_value_compare_key(lhs) == logic_value_compare_key(rhs_value);
            return (neq ? !eq : eq) ? Tri::True : Tri::False;
        }
        return value_to_bool(value_for(name));
    }

    Tri parse_and() {
        Tri v = parse_primary();
        while (eat("&&")) v = tri_and(v, parse_primary());
        return v;
    }

    Tri parse_or() {
        Tri v = parse_and();
        while (eat("||")) v = tri_or(v, parse_and());
        return v;
    }

    std::string text_;
    Json values_;
    size_t pos_;
    bool ok_;
};

} // namespace

const char* tri_text(Tri v) {
    if (v == Tri::True) return "true";
    if (v == Tri::False) return "false";
    return "unknown";
}

Tri evaluate_expression(const std::string& expr, const Json& values, bool& ok) {
    ExprParser parser(expr, values);
    Tri value = parser.parse();
    ok = parser.ok();
    return value;
}

} // namespace xdebug_waveform
