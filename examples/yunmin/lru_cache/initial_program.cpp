#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <deque>
#include <fstream>
#include <iostream>
#include <list>
#include <random>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

static std::vector<int> GenerateTrace(int seed, int length, int keyspace) {
    std::mt19937 rng(seed);
    std::uniform_real_distribution<double> prob(0.0, 1.0);
    std::uniform_int_distribution<int> hot(0, keyspace / 5);
    std::uniform_int_distribution<int> cold(0, keyspace);
    std::vector<int> trace;
    trace.reserve(length);
    for (int i = 0; i < length; ++i) {
        if (prob(rng) < 0.7) trace.push_back(hot(rng));
        else trace.push_back(cold(rng));
    }
    return trace;
}

static int ReferenceHits(const std::vector<int> &trace, int capacity) {
    std::list<int> order;
    std::unordered_map<int, std::list<int>::iterator> map;
    int hits = 0;
    for (int key : trace) {
        auto it = map.find(key);
        if (it != map.end()) {
            hits++;
            order.splice(order.end(), order, it->second);
            it->second = std::prev(order.end());
        } else {
            if (static_cast<int>(order.size()) >= capacity) {
                int evict = order.front();
                order.pop_front();
                map.erase(evict);
            }
            order.push_back(key);
            map[key] = std::prev(order.end());
        }
    }
    return hits;
}

// EVOLVE-BLOCK-START

class LRUCache {
public:
    explicit LRUCache(int capacity) : capacity_(capacity) {
        if (capacity_ <= 0) throw std::runtime_error("capacity must be positive");
    }

    bool access(int key) {
        auto it = map_.find(key);
        if (it != map_.end()) {
            order_.splice(order_.end(), order_, it->second);
            it->second = std::prev(order_.end());
            return true;
        }
        if (static_cast<int>(order_.size()) >= capacity_) {
            int evict = order_.front();
            order_.pop_front();
            map_.erase(evict);
        }
        order_.push_back(key);
        map_[key] = std::prev(order_.end());
        return false;
    }

private:
    int capacity_;
    std::list<int> order_;
    std::unordered_map<int, std::list<int>::iterator> map_;
};

// EVOLVE-BLOCK-END

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
    int seed = 121;
    int length = 200000;
    int keyspace = 5000;
    int capacity = 1024;
    int rounds = 2;
    int batch = 2000;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json" && i + 1 < argc) json_path = argv[++i];
        else if (arg == "--seed" && i + 1 < argc) seed = std::atoi(argv[++i]);
        else if (arg == "--length" && i + 1 < argc) length = std::atoi(argv[++i]);
        else if (arg == "--keyspace" && i + 1 < argc) keyspace = std::atoi(argv[++i]);
        else if (arg == "--capacity" && i + 1 < argc) capacity = std::atoi(argv[++i]);
        else if (arg == "--rounds" && i + 1 < argc) rounds = std::atoi(argv[++i]);
        else if (arg == "--batch" && i + 1 < argc) batch = std::atoi(argv[++i]);
    }

    std::vector<int> trace = GenerateTrace(seed, length, keyspace);
    int expected_hits = ReferenceHits(trace, capacity);

    {
        LRUCache cache(capacity);
        int hits = 0;
        for (int key : trace) {
            if (cache.access(key)) hits++;
        }
        if (hits != expected_hits) {
            std::cerr << "hit count mismatch" << std::endl;
            return 2;
        }
    }

    std::vector<double> latencies;
    latencies.reserve((length / batch + 1) * rounds);
    long long total_ops = 0;
    double total_time = 0.0;

    for (int r = 0; r < rounds; ++r) {
        LRUCache cache(capacity);
        for (int i = 0; i < length; i += batch) {
            int end = std::min(length, i + batch);
            auto t0 = std::chrono::high_resolution_clock::now();
            for (int j = i; j < end; ++j) {
                cache.access(trace[j]);
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

    std::ostringstream os;
    os.setf(std::ios::fixed);
    os.precision(6);
    os << "{\"ops_per_sec\":" << ops_per_sec
       << ",\"p99_latency_us\":" << (p99 * 1e6) << "}";
    WriteJson(json_path, os.str());
    return 0;
}
