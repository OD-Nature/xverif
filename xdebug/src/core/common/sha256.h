#pragma once

#include <string>

namespace xdebug_core {

// Returns a lowercase SHA-256 digest for in-memory bytes.
std::string sha256_text(const std::string& text);
// Returns a lowercase SHA-256 digest for a regular file.  The error string is
// intentionally caller-facing and must not include file contents.
bool sha256_file(const std::string& path, std::string& digest, std::string& error);
// Deterministic recursive digest for a directory: sorted relative names, node
// types and regular-file bytes are covered.  It is used only for daidir
// provenance, where a directory cannot be represented by a file digest.
bool sha256_directory_tree(const std::string& path, std::string& digest, std::string& error);

} // namespace xdebug_core
