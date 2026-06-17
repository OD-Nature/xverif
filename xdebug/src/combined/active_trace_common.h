#pragma once

#include "api/json_types.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_hdl.h"
#include "npi_L1.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <sstream>
#include <string>
#include <unistd.h>
#include <vector>

namespace xdebug {

// ═══════════════════════════════════════════════════════════════════
// RAII guards
// ═══════════════════════════════════════════════════════════════════

class ScopedStdoutSilence {
public:
    ScopedStdoutSilence() : saved_(-1), sink_(-1) {
        std::fflush(stdout);
        saved_ = dup(STDOUT_FILENO);
        sink_ = open("/dev/null", O_WRONLY);
        if (saved_ >= 0 && sink_ >= 0) dup2(sink_, STDOUT_FILENO);
    }
    ~ScopedStdoutSilence() {
        std::fflush(stdout);
        if (saved_ >= 0) { dup2(saved_, STDOUT_FILENO); close(saved_); }
        if (sink_ >= 0) close(sink_);
    }
private:
    int saved_, sink_;
};

class NpiSessionGuard {
public:
    NpiSessionGuard() = default;
    NpiSessionGuard(const NpiSessionGuard&) = delete;
    NpiSessionGuard& operator=(const NpiSessionGuard&) = delete;
    ~NpiSessionGuard() { if (loaded_) npi_end(); }
    bool init(int argc, char** argv) {
        if (!npi_init(argc, argv)) return false;
        loaded_ = true; return true;
    }
    bool load_design(int argc, char** argv) {
        return loaded_ && npi_load_design(argc, argv) != 0;
    }
private:
    bool loaded_ = false;
};

class FsdbFileGuard {
public:
    explicit FsdbFileGuard(const std::string& p) : h_(npi_fsdb_open(p.c_str())) {}
    FsdbFileGuard(const FsdbFileGuard&) = delete;
    FsdbFileGuard& operator=(const FsdbFileGuard&) = delete;
    ~FsdbFileGuard() { if (h_) npi_fsdb_close(h_); }
    npiFsdbFileHandle get() const { return h_; }
    explicit operator bool() const { return h_ != nullptr; }
private:
    npiFsdbFileHandle h_ = nullptr;
};

class NpiHandleGuard {
public:
    explicit NpiHandleGuard(npiHandle h = nullptr) : h_(h) {}
    NpiHandleGuard(const NpiHandleGuard&) = delete;
    NpiHandleGuard& operator=(const NpiHandleGuard&) = delete;
    ~NpiHandleGuard() { if (h_) npi_release_handle(h_); }
    npiHandle get() const { return h_; }
    explicit operator bool() const { return h_ != nullptr; }
private:
    npiHandle h_ = nullptr;
};

// ═══════════════════════════════════════════════════════════════════
// NPI helpers
// ═══════════════════════════════════════════════════════════════════

inline std::string npi_string(int prop, npiHandle h) {
    const char* s = h ? npi_get_str(prop, h) : nullptr;
    return s ? s : "";
}

inline std::string current_executable() {
    char path[4096] = {};
    ssize_t n = readlink("/proc/self/exe", path, sizeof(path) - 1);
    return n > 0 ? std::string(path, static_cast<size_t>(n)) : "xdebug";
}

inline std::string handle_info(npiHandle h) {
    const char* s = h ? npi_ut_get_hdl_info(h, true, false) : nullptr;
    return s ? s : "";
}

inline std::string statement_kind(int type) {
    switch (type) {
    case npiContAssign:   return "assignment";
    case npiAssignment:   return "assignment";
    case npiForce:        return "force";
    case npiPort:         return "port_boundary";
    case npiIf:           return "if";
    case npiIfElse:       return "if_else";
    case npiCase:         return "case";
    case npiCaseItem:     return "case_item";
    case npiEventControl: return "event_control";
    case npiRelease:      return "release";
#ifdef npiMpPort
    case npiMpPort:       return "modport_port";
#endif
#ifdef npiRefObj
    case npiRefObj:       return "ref_obj";
#endif
    default:
        if (type == 697) return "modport_port";
        if (type == 608) return "ref_obj";
        return "other";
    }
}

inline bool parse_time(const std::string& s, double& val, std::string& unit) {
    char* end = nullptr;
    val = std::strtod(s.c_str(), &end);
    if (!end || end == s.c_str()) return false;
    while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
    unit = end;
    if (unit == "f") unit = "fs"; else if (unit == "p") unit = "ps";
    else if (unit == "n") unit = "ns"; else if (unit == "u") unit = "us";
    else if (unit == "m") unit = "ms";
    return !unit.empty();
}

inline std::string fsdb_value_at(npiFsdbFileHandle fsdb,
                                  const std::string& sig, const std::string& t) {
    if (!fsdb) return "";
    npiFsdbSigHandle sh = npi_fsdb_sig_by_name(fsdb, sig.c_str(), nullptr);
    if (!sh) return "";
    double tv; std::string unit;
    if (!parse_time(t, tv, unit)) return "";
    npiFsdbTime ft = 0;
    if (!npi_fsdb_convert_time_in(fsdb, tv, unit.c_str(), ft)) return "";
    std::string raw;
    int rc = npi_fsdb_sig_hdl_value_at(sh, ft, raw, npiFsdbBinStrVal);
    return rc ? raw : "";
}

inline std::string format_value(const std::string& raw) {
    if (raw.empty()) return "?";
    bool known = raw.find_first_of("xXzZ") == std::string::npos;
    if (!known) return raw;
    unsigned long long v = 0;
    for (char c : raw) { v <<= 1; if (c == '1') v |= 1; }
    std::ostringstream ss;
    ss << raw.size() << "'h" << std::hex << v;
    return ss.str();
}

inline std::string driver_text(npiHandle h, const std::string& kind) {
    if (!h) return "(primary input)";
    std::string raw = handle_info(h);
    size_t comma = raw.find(", ");
    if (comma != std::string::npos) raw = raw.substr(comma + 2);
    size_t brace = raw.rfind(" {");
    if (brace != std::string::npos) raw = raw.substr(0, brace);
    return raw.empty() ? "(" + kind + ")" : raw;
}

} // namespace xdebug
