#include "core/common/sha256.h"
#include "test_temp_path.h"

#include <cassert>
#include <cstdio>
#include <sys/stat.h>
#include <unistd.h>

int main() {
    std::vector<char> root_storage = test_temp_template("xdebug-test-sha256.XXXXXX");
    char* root = mkdtemp(root_storage.data());
    assert(root != nullptr);
    const std::string path = std::string(root) + "/input";
    FILE* output = std::fopen(path.c_str(), "wb");
    assert(output);
    std::fputs("abc", output);
    std::fclose(output);
    std::string digest, error;
    assert(xdebug_core::sha256_file(path, digest, error));
    assert(digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    std::remove(path.c_str());
    const std::string directory = std::string(root) + "/tree";
    mkdir(directory.c_str(), 0700);
    std::string member = directory + "/member";
    output = std::fopen(member.c_str(), "wb");
    assert(output); std::fputs("one", output); std::fclose(output);
    std::string first_tree;
    assert(xdebug_core::sha256_directory_tree(directory, first_tree, error));
    output = std::fopen(member.c_str(), "wb");
    assert(output); std::fputs("two", output); std::fclose(output);
    std::string second_tree;
    assert(xdebug_core::sha256_directory_tree(directory, second_tree, error));
    assert(first_tree != second_tree);
    std::remove(member.c_str()); rmdir(directory.c_str()); rmdir(root);
    return 0;
}
