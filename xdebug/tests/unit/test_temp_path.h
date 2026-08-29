#pragma once

#include <cstdlib>
#include <string>
#include <sys/stat.h>
#include <vector>

inline std::string test_temp_root() {
    const char* configured = std::getenv("XVERIF_TEST_TMPDIR");
    std::string path = configured && configured[0] != '\0' ? configured : "tmp";
    mkdir(path.c_str(), 0700);
    return path;
}

inline std::vector<char> test_temp_template(const std::string& name) {
    std::string path = test_temp_root() + "/" + name;
    return std::vector<char>(path.begin(), path.end() + 1);
}
