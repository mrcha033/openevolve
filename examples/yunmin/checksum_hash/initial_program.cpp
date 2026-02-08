#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <random>
#include <sstream>
#include <string>
#include <vector>

static const uint32_t FNV_OFFSET_BASIS = 2166136261u;
static const uint32_t FNV_PRIME = 16777619u;

static uint32_t ReferenceHash(const std::vector<uint8_t> &data) {
    uint32_t h = FNV_OFFSET_BASIS;
    for (uint8_t b : data) {
        h ^= b;
        h *= FNV_PRIME;
    }
    return h;
}

// EVOLVE-BLOCK-START

static uint32_t Checksum32(const std::vector<uint8_t> &data) {
    uint32_t h = FNV_OFFSET_BASIS;
    for (uint8_t b : data) {
        h ^= b;
        h *= FNV_PRIME;
    }
    return h;
}

// EVOLVE-BLOCK-END

static std::vector<uint8_t> GenerateBuffer(std::mt19937 &rng, int size) {
    std::uniform_int_distribution<int> byte_dist(0, 255);
    std::vector<uint8_t> buf;
    buf.reserve(size);
    for (int i = 0; i < size; ++i) {
        buf.push_back(static_cast<uint8_t>(byte_dist(rng)));
    }
    return buf;
}

static void WriteJson(const std::string &path, const std::string &payload) {
    if (path.empty()) {
        std::cout << payload << std::endl;
        return;
    }
    std::ofstream out(path.c_str(), std::ios::binary);
    out << payload;
}

int main(int argc, char **argv) {
    std::string json_path;
    int seed = 999;
    int count = 4000;
    int size = 512;
    int rounds = 2;
    int batch = 200;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json" && i + 1 < argc) json_path = argv[++i];
        else if (arg == "--seed" && i + 1 < argc) seed = std::atoi(argv[++i]);
        else if (arg == "--count" && i + 1 < argc) count = std::atoi(argv[++i]);
        else if (arg == "--size" && i + 1 < argc) size = std::atoi(argv[++i]);
        else if (arg == "--rounds" && i + 1 < argc) rounds = std::atoi(argv[++i]);
        else if (arg == "--batch" && i + 1 < argc) batch = std::atoi(argv[++i]);
    }

    std::mt19937 rng(seed);
    std::vector<std::vector<uint8_t>> dataset;
    dataset.reserve(count);
    for (int i = 0; i < count; ++i) {
        dataset.push_back(GenerateBuffer(rng, size));
    }

    for (int i = 0; i < count; ++i) {
        uint32_t ref = ReferenceHash(dataset[i]);
        uint32_t got = Checksum32(dataset[i]);
        if (ref != got) {
            std::cerr << "checksum mismatch" << std::endl;
            return 2;
        }
    }

    std::vector<double> latencies;
    latencies.reserve((count / batch + 1) * rounds);
    long long total_ops = 0;
    double total_time = 0.0;
    long long total_bytes = 0;

    for (int r = 0; r < rounds; ++r) {
        for (int i = 0; i < count; i += batch) {
            int end = std::min(count, i + batch);
            auto t0 = std::chrono::high_resolution_clock::now();
            for (int j = i; j < end; ++j) {
                Checksum32(dataset[j]);
                total_bytes += static_cast<long long>(dataset[j].size());
            }
            auto t1 = std::chrono::high_resolution_clock::now();
            std::chrono::duration<double> dt = t1 - t0;
            int batch_size = end - i;
            total_ops += batch_size;
            total_time += dt.count();
            if (batch_size > 0) latencies.push_back(dt.count() / batch_size);
        }
    }

    if (total_time <= 0) total_time = 1e-9;
    double ops_per_sec = total_ops / total_time;
    std::sort(latencies.begin(), latencies.end());
    double p99 = latencies.empty() ? 0.0 : latencies[static_cast<size_t>(0.99 * (latencies.size() - 1))];
    double gb_per_sec = (total_bytes / (1024.0 * 1024.0 * 1024.0)) / total_time;

    std::ostringstream os;
    os.setf(std::ios::fixed);
    os.precision(6);
    os << "{\"ops_per_sec\":" << ops_per_sec
       << ",\"p99_latency_us\":" << (p99 * 1e6)
       << ",\"gb_per_sec\":" << gb_per_sec << "}";
    WriteJson(json_path, os.str());
    return 0;
}
