#include "waveform_exporter.h"

#include "../server/fsdb_value_reader.h"
#include "../server/fsdb_scan_utils.h"
#include "../server/server_internal.h"

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <sys/stat.h>
#include <vector>

namespace xdebug_waveform {

namespace {

struct ExportRow {
    npiFsdbTime time = 0;
    std::string bits;
    ExportRow() {}
    ExportRow(npiFsdbTime t, const std::string& b) : time(t), bits(b) {}
};

bool ensure_dir(const std::string& path) {
    if (path.empty()) return false;
    struct stat st;
    if (stat(path.c_str(), &st) == 0) return S_ISDIR(st.st_mode);
    size_t pos = 0;
    while (true) {
        pos = path.find('/', pos + 1);
        std::string part = pos == std::string::npos ? path : path.substr(0, pos);
        if (part.empty()) continue;
        if (mkdir(part.c_str(), 0700) != 0) {
            if (stat(part.c_str(), &st) != 0 || !S_ISDIR(st.st_mode)) return false;
        }
        if (pos == std::string::npos) break;
    }
    return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

std::string sanitize_name(const std::string& text, size_t index) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '_' || c == '-') {
            out.push_back(c);
        } else {
            out.push_back('_');
        }
    }
    if (out.empty()) out = "signal";
    if (out.size() > 96) out = out.substr(out.size() - 96);
    std::ostringstream oss;
    oss << std::setw(4) << std::setfill('0') << index << "_" << out;
    return oss.str();
}

std::string bits_only(std::string value) {
    if (value.size() >= 2 && value[0] == '\'' &&
        (value[1] == 'b' || value[1] == 'B')) {
        value = value.substr(2);
    }
    for (char& c : value) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    return value;
}

uint64_t word_from_bits(const std::string& bits, size_t word_index, bool known_mask) {
    uint64_t word = 0;
    const size_t width = bits.size();
    const size_t base = word_index * 64;
    for (size_t bit = 0; bit < 64; ++bit) {
        size_t from_right = base + bit;
        if (from_right >= width) break;
        char c = bits[width - 1 - from_right];
        bool known = c == '0' || c == '1';
        if (known_mask) {
            if (known) word |= (1ULL << bit);
        } else if (c == '1') {
            word |= (1ULL << bit);
        }
    }
    return word;
}

std::string hex_from_words(const std::string& bits, bool known_mask) {
    size_t word_count = std::max<size_t>(1, (bits.size() + 63) / 64);
    std::ostringstream oss;
    oss << "0x";
    bool emitted = false;
    for (size_t i = word_count; i > 0; --i) {
        uint64_t word = word_from_bits(bits, i - 1, known_mask);
        if (!emitted) {
            if (word == 0 && i > 1) continue;
            oss << std::hex << word;
            emitted = true;
        } else {
            oss << std::setw(16) << std::setfill('0') << std::hex << word;
        }
    }
    if (!emitted) oss << "0";
    return oss.str();
}

bool write_u64_le(std::ofstream& out, uint64_t value) {
    char bytes[8];
    for (int i = 0; i < 8; ++i) bytes[i] = static_cast<char>((value >> (i * 8)) & 0xff);
    out.write(bytes, sizeof(bytes));
    return static_cast<bool>(out);
}

bool write_binary_file(const std::string& path,
                       const std::vector<ExportRow>& rows,
                       size_t word_count,
                       std::string& error) {
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        error = "failed to open export file: " + path;
        return false;
    }
    for (const auto& row : rows) {
        if (!write_u64_le(out, static_cast<uint64_t>(row.time))) return false;
        for (size_t i = 0; i < word_count; ++i) {
            if (!write_u64_le(out, word_from_bits(row.bits, i, false))) return false;
        }
        for (size_t i = 0; i < word_count; ++i) {
            if (!write_u64_le(out, word_from_bits(row.bits, i, true))) return false;
        }
    }
    if (!out) {
        error = "failed to write export file: " + path;
        return false;
    }
    return true;
}

bool write_tsv_file(const std::string& path,
                    const std::vector<ExportRow>& rows,
                    std::string& error) {
    std::ofstream out(path);
    if (!out) {
        error = "failed to open export file: " + path;
        return false;
    }
    out << "time\tvalue_hex\tknown_hex\n";
    for (const auto& row : rows) {
        out << format_time(row.time) << '\t' << hex_from_words(row.bits, false)
            << '\t' << hex_from_words(row.bits, true) << '\n';
    }
    if (!out) {
        error = "failed to write export file: " + path;
        return false;
    }
    return true;
}

bool collect_rows(npiFsdbFileHandle file,
                  const std::string& signal,
                  npiFsdbTime begin,
                  npiFsdbTime end,
                  std::vector<ExportRow>& rows,
                  size_t& width,
                  std::string& error) {
    rows.clear();
    width = 0;
    std::string begin_value;
    if (!read_sig_value_at(file, signal.c_str(), begin, 'B', begin_value)) {
        error = "failed to read begin value for signal: " + signal;
        return false;
    }
    rows.push_back({begin, bits_only(begin_value)});
    width = std::max(width, rows.back().bits.size());

    fsdbTimeValPairVec_t changes;
    if (!read_signal_changes(signal, begin, end, npiFsdbBinStrVal, changes, error, -1, nullptr)) {
        return false;
    }
    for (const auto& change : changes) {
        std::string bits = bits_only(change.second);
        if (!rows.empty() && rows.back().time == change.first) {
            rows.back().bits = bits;
        } else {
            rows.push_back({change.first, bits});
        }
        width = std::max(width, bits.size());
    }
    if (width == 0) width = 1;
    return true;
}

} // namespace

bool export_signal_list(npiFsdbFileHandle file,
                        const SignalList& list,
                        const ListExportOptions& options,
                        ListExportResult& result,
                        std::string& error) {
    if (!file) {
        error = "FSDB file is not open";
        return false;
    }
    if (list.signals.empty()) {
        error = "List is empty: " + list.name;
        return false;
    }
    std::string format = options.format.empty() ? "u64bin" : options.format;
    if (format != "u64bin" && format != "hex_tsv") {
        error = "format must be u64bin or hex_tsv";
        return false;
    }
    if (!ensure_dir(options.output_dir)) {
        error = "failed to create export directory: " + options.output_dir;
        return false;
    }

    Json manifest;
    manifest["version"] = 1;
    manifest["format"] = format == "u64bin" ? "u64bin.v1" : "hex_tsv.v1";
    manifest["list"] = list.name;
    auto range = format_time_range(options.begin, options.end);
    manifest["begin"] = range.first;
    manifest["end"] = range.second;
    manifest["row_layout"] = format == "u64bin"
        ? "uint64_le: time_tick, value_words, known_mask_words"
        : "tsv: time, value_hex, known_hex";
    manifest["signals"] = Json::array();

    size_t total_rows = 0;
    for (size_t i = 0; i < list.signals.size(); ++i) {
        const std::string& signal = list.signals[i];
        std::vector<ExportRow> rows;
        size_t width = 0;
        if (!collect_rows(file, signal, options.begin, options.end, rows, width, error)) {
            return false;
        }
        size_t word_count = std::max<size_t>(1, (width + 63) / 64);
        std::string stem = sanitize_name(signal, i + 1);
        std::string filename = stem + (format == "u64bin" ? ".u64bin" : ".tsv");
        std::string path = options.output_dir + "/" + filename;
        bool ok = format == "u64bin"
            ? write_binary_file(path, rows, word_count, error)
            : write_tsv_file(path, rows, error);
        if (!ok) return false;

        Json item;
        item["index"] = i;
        item["signal"] = signal;
        item["file"] = filename;
        item["row_count"] = rows.size();
        item["width"] = width;
        item["word_count"] = word_count;
        item["columns"] = format == "u64bin" ? (1 + word_count * 2) : 3;
        manifest["signals"].push_back(item);
        total_rows += rows.size();
    }

    manifest["signal_count"] = list.signals.size();
    manifest["row_count"] = total_rows;

    std::string manifest_file = options.output_dir + "/manifest.json";
    std::ofstream mf(manifest_file);
    if (!mf) {
        error = "failed to open manifest file: " + manifest_file;
        return false;
    }
    mf << manifest.dump(2) << "\n";
    if (!mf) {
        error = "failed to write manifest file: " + manifest_file;
        return false;
    }

    result.output_dir = options.output_dir;
    result.manifest_file = manifest_file;
    result.format = manifest["format"].get<std::string>();
    result.signal_count = list.signals.size();
    result.row_count = total_rows;
    result.signals = manifest["signals"];
    return true;
}

} // namespace xdebug_waveform
