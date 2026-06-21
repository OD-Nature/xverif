#include "../server_internal.h"
#include "session/session_types.h"
#include "waveform/value/logic_value.h"

namespace xdebug_waveform {

using Json = nlohmann::ordered_json;

// Global for cleanup
std::string g_session_id;
int g_srv_fd = -1;
char g_sock_path[SOCK_PATH_LEN];
std::string g_transport = "uds";
std::string g_bind_host;
std::string g_host;
int g_port = 0;
std::string g_auth_token;
npiFsdbFileHandle g_fsdb_file = nullptr;
std::string g_fsdb_file_path;
long g_fsdb_mtime = 0;
long long g_fsdb_size = 0;
unsigned long long g_fsdb_dev = 0;
unsigned long long g_fsdb_inode = 0;
xdebug_waveform::ApbAnalyzer g_apb_analyzer;
xdebug_waveform::AxiAnalyzer g_axi_analyzer;
xdebug_waveform::EventAnalyzer g_event_analyzer;
FILE* g_debug_log = nullptr;

bool server_debug_enabled() {
    const char* env = getenv("XDEBUG_WAVEFORM_DEBUG");
    return env && env[0] != '\0' && strcmp(env, "0") != 0 &&
           strcasecmp(env, "false") != 0 && strcasecmp(env, "off") != 0;
}

void server_debug_open_log() {
    if (!server_debug_enabled() || g_session_id.empty()) return;
    char log_path[SOCK_PATH_LEN];
    get_debug_log_path(log_path, g_session_id);
    g_debug_log = fopen(log_path, "a");
    if (g_debug_log) {
        time_t now = time(nullptr);
        fprintf(g_debug_log, "=== xdebug_waveform server debug session=%s time=%ld ===\n",
                g_session_id.c_str(), static_cast<long>(now));
        fflush(g_debug_log);
    }
}

void server_debug_log(const char* fmt, ...) {
    if (!g_debug_log) return;
    fprintf(g_debug_log, "[server] ");
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_debug_log, fmt, ap);
    va_end(ap);
    fprintf(g_debug_log, "\n");
    fflush(g_debug_log);
}

void cleanup_and_exit(int sig) {
    server_debug_log("cleanup_and_exit: signal=%d", sig);
    if (g_srv_fd >= 0) {
        close(g_srv_fd);
    }
    if (strlen(g_sock_path) > 0) {
        unlink(g_sock_path);
    }
    if (g_fsdb_file) {
        npi_fsdb_close(g_fsdb_file);
        g_fsdb_file = nullptr;
    }
    if (!g_session_id.empty()) {
        SessionRegistry registry;
        registry.remove(g_session_id);
    }
    npi_end();
    if (g_debug_log) {
        server_debug_log("cleanup_and_exit: done");
        fclose(g_debug_log);
        g_debug_log = nullptr;
    }
    exit(0);
}

void daemonize_io() {
    int devnull = open("/dev/null", O_RDWR);
    if (devnull >= 0) {
        dup2(devnull, STDIN_FILENO);
        dup2(devnull, STDOUT_FILENO);
        dup2(devnull, STDERR_FILENO);
        close(devnull);
    }
}

bool send_all(int fd, const char* buf, size_t len) {
    size_t sent = 0;
    while (sent < len) {
        ssize_t n = write(fd, buf + sent, len - sent);
        if (n <= 0) return false;
        sent += n;
    }
    return true;
}

bool read_command_line(int fd, char* line, size_t line_size) {
    if (!line || line_size == 0) return false;
    size_t total = 0;
    while (total < line_size - 1) {
        ssize_t n = read(fd, line + total, 1);
        if (n <= 0) return false;
        if (line[total] == '\n') break;
        total++;
    }
    line[total] = '\0';
    return true;
}

char* trim_command(char* cmd) {
    while (*cmd == ' ' || *cmd == '\t') cmd++;
    size_t len = strlen(cmd);
    while (len > 0 && (cmd[len - 1] == '\n' || cmd[len - 1] == '\r' || cmd[len - 1] == ' ')) {
        cmd[len - 1] = '\0';
        len--;
    }
    return cmd;
}

std::string json_response(const Json& j) {
    return j.dump() + "\n" + END_MARKER;
}

bool contains_xz_value(const std::string& value) {
    return logic_value_has_xz(logic_value_from_fsdb_raw(value, 'h'));
}

std::string with_value_prefix(const std::string& value, char prefix) {
    if (value.size() >= 2 && value[0] == '\'') return value;
    char p = static_cast<char>(std::tolower(static_cast<unsigned char>(prefix)));
    return std::string("'") + p + value;
}

Json wave_value_json(const std::string& raw, char prefix) {
    return logic_value_json(logic_value_from_fsdb_raw(raw, prefix));
}

bool stat_fsdb(long& mtime,
                      long long& size,
                      unsigned long long& dev,
                      unsigned long long& inode) {
    struct stat st;
    if (stat(g_fsdb_file_path.c_str(), &st) != 0) return false;
    mtime = static_cast<long>(st.st_mtime);
    size = static_cast<long long>(st.st_size);
    dev = static_cast<unsigned long long>(st.st_dev);
    inode = static_cast<unsigned long long>(st.st_ino);
    return true;
}

bool fsdb_changed() {
    long mtime = 0;
    long long size = 0;
    unsigned long long dev = 0;
    unsigned long long inode = 0;
    if (!stat_fsdb(mtime, size, dev, inode)) return true;
    return !xdebug_core::resource_content_matches(g_fsdb_mtime,
                                                  g_fsdb_size,
                                                  mtime,
                                                  size);
}

void send_error(int client_fd, const std::string& message) {
    std::string err = std::string(ERROR_PREFIX) + message + "\n" + END_MARKER;
    send_all(client_fd, err.c_str(), err.length());
}

std::string fsdb_time_scale() {
    const char* scale = g_fsdb_file ? npi_fsdb_time_scale_unit(g_fsdb_file) : nullptr;
    return scale ? scale : "unknown";
}

bool convert_duration_to_time(const DurationSpec& duration,
                                     npiFsdbTime& out_time,
                                     std::string& error) {
    if (duration.cycle) {
        error = "TIME_SPEC_INVALID: cycle duration requires a cursor or around base time";
        return false;
    }
    if (duration.value < 0) {
        error = "TIME_SPEC_INVALID: negative duration is not allowed here";
        return false;
    }
    if (!g_fsdb_file ||
        !npi_fsdb_convert_time_in(g_fsdb_file,
                                  duration.value,
                                  duration.unit.c_str(),
                                  out_time)) {
        error = "Failed to convert TimeSpec duration for FSDB scale " + fsdb_time_scale();
        return false;
    }
    return true;
}

bool resolve_cycle_offset(npiFsdbTime base,
                                 const DurationSpec& offset,
                                 npiFsdbTime& out_time,
                                 std::string& error) {
    if (!std::isfinite(offset.value)) {
        error = "TIME_SPEC_INVALID: cycle offset is not finite";
        return false;
    }
    double rounded = std::round(offset.value);
    if (std::fabs(offset.value - rounded) > 1e-9) {
        error = "TIME_SPEC_INVALID: cycle offset must be an integer";
        return false;
    }
    long long cycles = static_cast<long long>(rounded);
    if (cycles == 0) {
        out_time = base;
        return true;
    }
    npiFsdbSigHandle clk = npi_fsdb_sig_by_name(g_fsdb_file, offset.clock.c_str(), NULL);
    if (!clk) {
        error = "SIGNAL_NOT_FOUND: Clock signal not found: " + offset.clock;
        return false;
    }
    ClockEdgeCursor cursor(clk, offset.posedge);
    if (!cursor.valid()) {
        error = "WAVE_QUERY_FAILED: failed to create clock edge cursor for " + offset.clock;
        return false;
    }

    npiFsdbTime edge_time = 0;
    if (cycles > 0) {
        if (!cursor.first_at_or_after(base, edge_time)) {
            error = "TIME_OUT_OF_RANGE: no clock edge after cursor time";
            return false;
        }
        if (edge_time <= base && !cursor.next(edge_time)) {
            error = "TIME_OUT_OF_RANGE: no clock edge after cursor time";
            return false;
        }
        for (long long i = 1; i < cycles; ++i) {
            if (!cursor.next(edge_time)) {
                error = "TIME_OUT_OF_RANGE: cycle offset exceeds waveform end";
                return false;
            }
        }
    } else {
        if (!cursor.prev_before(base, edge_time)) {
            error = "TIME_OUT_OF_RANGE: no clock edge before cursor time";
            return false;
        }
        for (long long i = -1; i > cycles; --i) {
            if (!cursor.prev_before(edge_time, edge_time)) {
                error = "TIME_OUT_OF_RANGE: cycle offset is before waveform start";
                return false;
            }
        }
    }
    out_time = edge_time;
    return true;
}

bool apply_duration_offset(npiFsdbTime base,
                                  DurationSpec offset,
                                  npiFsdbTime& out_time,
                                  std::string& error) {
    if (offset.cycle) {
        return resolve_cycle_offset(base, offset, out_time, error);
    }
    npiFsdbTime delta = 0;
    double sign = offset.value < 0 ? -1.0 : 1.0;
    offset.value = std::fabs(offset.value);
    if (!convert_duration_to_time(offset, delta, error)) return false;
    if (sign < 0) {
        if (base < delta) {
            error = "TIME_OUT_OF_RANGE: resolved time is before waveform start";
            return false;
        }
        out_time = base - delta;
    } else {
        out_time = base + delta;
        if (out_time < base) {
            error = "TIME_OUT_OF_RANGE: resolved time is after waveform end";
            return false;
        }
    }
    return true;
}

bool parse_user_time(const char* text,
                            bool allow_max,
                            npiFsdbTime& out_time,
                            std::string& error) {
    if (!text || text[0] == '\0') {
        error = "Invalid time: empty";
        return false;
    }
    if (allow_max && (strcasecmp(text, "max") == 0 || strcasecmp(text, "inf") == 0)) {
        out_time = 0xFFFFFFFFFFFFFFFFULL;
        return true;
    }
    ParsedTimeSpec spec;
    if (!parse_time_spec_text(text, spec, error)) return false;

    auto convert_abs = [&](const std::string& source, npiFsdbTime& out) -> bool {
        if (source.empty() || source[0] == '-') {
            error = std::string("Invalid time '") + source + "': negative time is not allowed";
            return false;
        }
        char* end = nullptr;
        errno = 0;
        double value = strtod(source.c_str(), &end);
        if (errno != 0 || end == source.c_str() || !std::isfinite(value) || value < 0) {
            error = std::string("Invalid time '") + source + "'";
            return false;
        }
        while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
        const char* unit = "ns";
        if (*end != '\0') {
            if (strcasecmp(end, "us") == 0) unit = "us";
            else if (strcasecmp(end, "ns") == 0) unit = "ns";
            else if (strcasecmp(end, "ps") == 0) unit = "ps";
            else if (strcasecmp(end, "fs") == 0) unit = "fs";
            else {
                error = std::string("Invalid time '") + source
                      + "': unsupported unit, expected us/ns/ps/fs (FSDB scale "
                      + fsdb_time_scale() + ")";
                return false;
            }
        }
        npiFsdbTime converted = 0;
        if (!g_fsdb_file || !npi_fsdb_convert_time_in(g_fsdb_file, value, unit, converted)) {
            error = std::string("Failed to convert time '") + source
                  + "' for FSDB scale " + fsdb_time_scale();
            return false;
        }
        out = converted;
        return true;
    };

    if (spec.kind == TimeSpecKind::Absolute) {
        return convert_abs(spec.absolute_text, out_time);
    }

    std::string cursor_name = spec.cursor_name;
    CursorManager cm;
    if (spec.use_active_cursor && !cm.get_active_cursor(g_session_id, cursor_name)) {
        error = "CURSOR_NOT_FOUND: active cursor is not set";
        return false;
    }
    Cursor cursor;
    if (!cm.get_cursor(g_session_id, cursor_name, cursor)) {
        error = "CURSOR_NOT_FOUND: Cursor '" + cursor_name + "' does not exist";
        return false;
    }
    uint64_t resolved = cursor.time;
    if (spec.has_offset) {
        npiFsdbTime adjusted = 0;
        if (!apply_duration_offset(resolved, spec.offset, adjusted, error)) return false;
        resolved = adjusted;
    }
    out_time = static_cast<npiFsdbTime>(resolved);
    return true;
}

bool read_list_from_storage(const std::string& session_id, const char* list_name, SignalList& out_list) {
    ListManager lm;
    return lm.get_list(session_id, list_name, out_list);
}

std::string format_time(npiFsdbTime t) {
    auto format_number = [](double value) {
        char buf[64];
        double rounded = std::round(value);
        if (std::fabs(value - rounded) < 1e-9) {
            snprintf(buf, sizeof(buf), "%.0f", rounded);
        } else {
            snprintf(buf, sizeof(buf), "%.6g", value);
        }
        return std::string(buf);
    };

    if (g_fsdb_file) {
        double us = 0.0;
        if (npi_fsdb_convert_time_out(g_fsdb_file, t, "us", us) && us >= 1.0 &&
            std::fabs(us - std::round(us)) < 1e-9) {
            return format_number(us) + "us";
        }
        double ns = 0.0;
        if (npi_fsdb_convert_time_out(g_fsdb_file, t, "ns", ns) && ns >= 1.0 &&
            std::fabs(ns - std::round(ns)) < 1e-9) {
            return format_number(ns) + "ns";
        }
        double ps = 0.0;
        if (npi_fsdb_convert_time_out(g_fsdb_file, t, "ps", ps)) {
            return format_number(ps) + "ps";
        }
    }

    if (t % 1000000 == 0 && t >= 1000000) {
        return std::to_string(t / 1000000) + "us";
    }
    if (t % 1000 == 0 && t >= 1000) {
        return std::to_string(t / 1000) + "ns";
    }
    return std::to_string(t) + "ps";
}

bool json_time_range(const Json& args,
                            npiFsdbTime& begin,
                            npiFsdbTime& end,
                            std::string& error) {
    begin = 0;
    end = 0xFFFFFFFFFFFFFFFFULL;
    Json tr = args.value("time_range", Json::object());
    bool has_begin = (tr.is_object() && (tr.contains("begin") || tr.contains("from"))) || args.contains("begin") || args.contains("from");
    bool has_end   = (tr.is_object() && (tr.contains("end")   || tr.contains("to")))   || args.contains("end")   || args.contains("to");
    if (has_begin || has_end || !args.contains("around")) {
        auto read_time_key = [&](const char* primary, const char* alias, const char* default_val) -> std::string {
            if (tr.is_object()) {
                if (tr.contains(primary)) return tr[primary].get<std::string>();
                if (tr.contains(alias))   return tr[alias].get<std::string>();
            }
            if (args.contains(primary)) return args[primary].get<std::string>();
            if (args.contains(alias))   return args[alias].get<std::string>();
            return default_val;
        };
        std::string begin_s = read_time_key("begin", "from", "0ns");
        std::string end_s   = read_time_key("end",   "to",   "max");
        return parse_user_time(begin_s.c_str(), false, begin, error) &&
               parse_user_time(end_s.c_str(), true, end, error);
    }

    std::string around_s = args.value("around", std::string());
    npiFsdbTime around = 0;
    if (!parse_user_time(around_s.c_str(), false, around, error)) return false;

    auto apply_window_duration = [&](const std::string& text,
                                     bool before,
                                     npiFsdbTime& out) -> bool {
        DurationSpec duration;
        if (!parse_duration_spec(text, duration, error)) return false;
        if (duration.value < 0) {
            error = "TIME_SPEC_INVALID: before/after duration must be non-negative";
            return false;
        }
        if (before) duration.value = -duration.value;
        return apply_duration_offset(around, duration, out, error);
    };

    std::string before_s = args.value("before", std::string("0ns"));
    std::string after_s = args.value("after", std::string("0ns"));
    return apply_window_duration(before_s, true, begin) &&
           apply_window_duration(after_s, false, end);
}

npiFsdbValType json_value_format(const Json& args) {
    std::string fmt = args.value("format", std::string("binary"));
    if (fmt == "hex" || fmt == "h") return npiFsdbHexStrVal;
    if (fmt == "decimal" || fmt == "dec" || fmt == "d") return npiFsdbDecStrVal;
    return npiFsdbBinStrVal;
}

std::string server_compact_expr_ws(const std::string& expr) {
    std::string out;
    for (char c : expr) {
        if (!std::isspace(static_cast<unsigned char>(c))) out.push_back(c);
    }
    return out;
}

char json_value_prefix(npiFsdbValType fmt) {
    if (fmt == npiFsdbHexStrVal) return 'h';
    if (fmt == npiFsdbDecStrVal) return 'd';
    return 'b';
}


}  // namespace xdebug_waveform
