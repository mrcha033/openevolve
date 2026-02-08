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

static const uint8_t MARKER = 0xFF;

static std::vector<uint8_t> ReferenceDecompress(const std::vector<uint8_t> &data) {
    std::vector<uint8_t> out;
    size_t i = 0;
    while (i < data.size()) {
        uint8_t b = data[i];
        if (b != MARKER) {
            out.push_back(b);
            ++i;
            continue;
        }
        if (i + 2 >= data.size()) throw std::runtime_error("truncated marker");
        uint8_t count = data[i + 1];
        uint8_t value = data[i + 2];
        if (count == 0) {
            out.push_back(value);
        } else {
            out.insert(out.end(), count, value);
        }
        i += 3;
    }
    return out;
}

// EVOLVE-BLOCK-START

static std::vector<uint8_t> Compress(const std::vector<uint8_t> &data) {
    std::vector<uint8_t> out;
    size_t n = data.size();
    size_t i = 0;
    while (i < n) {
        uint8_t b = data[i];
        size_t run_len = 1;
        size_t j = i + 1;
        while (j < n && data[j] == b && run_len < 255) {
            ++run_len;
            ++j;
        }
        if (run_len >= 3) {
            out.push_back(MARKER);
            out.push_back(static_cast<uint8_t>(run_len));
            out.push_back(b);
            i += run_len;
        } else {
            if (b == MARKER) {
                out.push_back(MARKER);
                out.push_back(0);
                out.push_back(MARKER);
            } else {
                out.push_back(b);
            }
            ++i;
        }
    }
    return out;
}

static std::vector<uint8_t> Decompress(const std::vector<uint8_t> &data) {
    return ReferenceDecompress(data);
}

// EVOLVE-BLOCK-END

static std::vector<uint8_t> GenerateBuffer(std::mt19937 &rng, int size) {
    std::uniform_real_distribution<double> prob(0.0, 1.0);
    std::uniform_int_distribution<int> byte_dist(0, 255);
    std::uniform_int_distribution<int> run_len_dist(3, 40);
    std::vector<uint8_t> buf;
    buf.reserve(size);
    while (static_cast<int>(buf.size()) < size) {
        if (prob(rng) < 0.6) {
            uint8_t b = static_cast<uint8_t>(byte_dist(rng));
            int len = run_len_dist(rng);
            for (int i = 0; i < len; ++i) buf.push_back(b);
        } else {
            buf.push_back(static_cast<uint8_t>(byte_dist(rng)));
        }
    }
    buf.resize(size);
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
    int seed = 777;
    int count = 2000;
    int size = 256;
    int rounds = 2;
    int batch = 50;

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
        std::vector<uint8_t> enc = Compress(dataset[i]);
        std::vector<uint8_t> ref = ReferenceDecompress(enc);
        std::vector<uint8_t> dec = Decompress(enc);
        if (ref != dataset[i] || dec != dataset[i]) {
            std::cerr << "round-trip mismatch" << std::endl;
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
                std::vector<uint8_t> enc = Compress(dataset[j]);
                std::vector<uint8_t> dec = Decompress(enc);
                if (dec != dataset[j]) {
                    std::cerr << "round-trip mismatch" << std::endl;
                    return 2;
                }
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
    double mb_per_sec = (total_bytes / (1024.0 * 1024.0)) / total_time;

    std::ostringstream os;
    os.setf(std::ios::fixed);
    os.precision(6);
    os << "{\"ops_per_sec\":" << ops_per_sec
       << ",\"p99_latency_us\":" << (p99 * 1e6)
       << ",\"mb_per_sec\":" << mb_per_sec << "}";
    WriteJson(json_path, os.str());
    return 0;
}
