#include "sha256.h"

#include <cstdio>
#include <cstring>
#include <stdint.h>
#include <dirent.h>
#include <sys/stat.h>
#include <algorithm>
#include <vector>

namespace xdebug_core {
namespace {

struct Sha256 {
    uint32_t h[8] = {0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
                     0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U};
    unsigned char block[64] = {};
    size_t used = 0;
    uint64_t bits = 0;
};

uint32_t rotr(uint32_t value, int count) { return (value >> count) | (value << (32 - count)); }
uint32_t choose(uint32_t x, uint32_t y, uint32_t z) { return (x & y) ^ (~x & z); }
uint32_t majority(uint32_t x, uint32_t y, uint32_t z) { return (x & y) ^ (x & z) ^ (y & z); }

void compress(Sha256& state, const unsigned char* block) {
    static const uint32_t k[64] = {
        0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
        0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
        0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
        0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
        0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
        0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
        0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
        0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U};
    uint32_t w[64];
    for (int i = 0; i < 16; ++i) w[i] = (static_cast<uint32_t>(block[4*i]) << 24) |
        (static_cast<uint32_t>(block[4*i+1]) << 16) | (static_cast<uint32_t>(block[4*i+2]) << 8) | block[4*i+3];
    for (int i = 16; i < 64; ++i) {
        uint32_t s0 = rotr(w[i-15], 7) ^ rotr(w[i-15], 18) ^ (w[i-15] >> 3);
        uint32_t s1 = rotr(w[i-2], 17) ^ rotr(w[i-2], 19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    uint32_t a=state.h[0], b=state.h[1], c=state.h[2], d=state.h[3], e=state.h[4], f=state.h[5], g=state.h[6], h=state.h[7];
    for (int i = 0; i < 64; ++i) {
        uint32_t s1 = rotr(e,6)^rotr(e,11)^rotr(e,25);
        uint32_t t1 = h + s1 + choose(e,f,g) + k[i] + w[i];
        uint32_t s0 = rotr(a,2)^rotr(a,13)^rotr(a,22);
        uint32_t t2 = s0 + majority(a,b,c);
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    state.h[0]+=a; state.h[1]+=b; state.h[2]+=c; state.h[3]+=d;
    state.h[4]+=e; state.h[5]+=f; state.h[6]+=g; state.h[7]+=h;
}

void update(Sha256& state, const unsigned char* input, size_t size) {
    state.bits += static_cast<uint64_t>(size) * 8U;
    while (size) {
        size_t copy = size < 64 - state.used ? size : 64 - state.used;
        std::memcpy(state.block + state.used, input, copy);
        state.used += copy; input += copy; size -= copy;
        if (state.used == 64) { compress(state, state.block); state.used = 0; }
    }
}

std::string finish(Sha256& state) {
    state.block[state.used++] = 0x80;
    if (state.used > 56) { while (state.used < 64) state.block[state.used++] = 0; compress(state, state.block); state.used = 0; }
    while (state.used < 56) state.block[state.used++] = 0;
    for (int i = 7; i >= 0; --i) state.block[state.used++] = static_cast<unsigned char>(state.bits >> (i * 8));
    compress(state, state.block);
    static const char hex[] = "0123456789abcdef";
    std::string out; out.reserve(64);
    for (int i = 0; i < 8; ++i) for (int shift = 28; shift >= 0; shift -= 4) out.push_back(hex[(state.h[i] >> shift) & 15]);
    return out;
}

bool update_regular_file(Sha256& state, const std::string& path, std::string& error) {
    FILE* input = std::fopen(path.c_str(), "rb");
    if (!input) { error = "cannot open file for SHA-256"; return false; }
    unsigned char buffer[32768];
    while (true) { size_t count = std::fread(buffer, 1, sizeof(buffer), input); if (count) update(state, buffer, count); if (count != sizeof(buffer)) break; }
    if (std::ferror(input)) { std::fclose(input); error = "cannot read file for SHA-256"; return false; }
    std::fclose(input); return true;
}

bool update_directory_tree(Sha256& state, const std::string& root, const std::string& relative, std::string& error) {
    DIR* directory = opendir(root.c_str());
    if (!directory) { error = "cannot open directory for SHA-256"; return false; }
    std::vector<std::string> names;
    while (dirent* entry = readdir(directory)) {
        std::string name(entry->d_name);
        if (name != "." && name != "..") names.push_back(name);
    }
    closedir(directory); std::sort(names.begin(), names.end());
    for (const auto& name : names) {
        const std::string child = root + "/" + name;
        const std::string child_relative = relative.empty() ? name : relative + "/" + name;
        struct stat st;
        if (lstat(child.c_str(), &st) != 0) { error = "cannot stat directory member for SHA-256"; return false; }
        if (S_ISDIR(st.st_mode)) {
            const std::string marker = "D\n" + child_relative + "\n";
            update(state, reinterpret_cast<const unsigned char*>(marker.data()), marker.size());
            if (!update_directory_tree(state, child, child_relative, error)) return false;
        } else if (S_ISREG(st.st_mode)) {
            const std::string marker = "F\n" + child_relative + "\n";
            update(state, reinterpret_cast<const unsigned char*>(marker.data()), marker.size());
            if (!update_regular_file(state, child, error)) return false;
        } else { error = "directory tree contains unsupported file type"; return false; }
    }
    return true;
}
} // namespace

std::string sha256_text(const std::string& text) {
    Sha256 state;
    update(state, reinterpret_cast<const unsigned char*>(text.data()), text.size());
    return finish(state);
}

bool sha256_file(const std::string& path, std::string& digest, std::string& error) {
    digest.clear(); error.clear();
    Sha256 state;
    if (!update_regular_file(state, path, error)) return false;
    digest = finish(state); return true;
}

bool sha256_directory_tree(const std::string& path, std::string& digest, std::string& error) {
    digest.clear(); error.clear(); Sha256 state;
    if (!update_directory_tree(state, path, "", error)) return false;
    digest = finish(state); return true;
}

} // namespace xdebug_core
