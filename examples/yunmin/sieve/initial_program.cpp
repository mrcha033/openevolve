#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

// --- Hardware Performance Counters (Linux perf_event_open, no sudo) ---
#ifdef __linux__
#include <linux/perf_event.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>
#endif

struct HWCounters {
    long long cycles = 0, instructions = 0;
    long long cache_misses = 0, cache_refs = 0;
    long long branch_misses = 0, branches = 0;
#ifdef __linux__
    int fds[6] = {-1,-1,-1,-1,-1,-1};
    void start() {
        auto open_ev = [](int cfg) {
            struct perf_event_attr pe{};
            pe.type = PERF_TYPE_HARDWARE; pe.size = sizeof(pe);
            pe.config = cfg; pe.disabled = 1;
            pe.exclude_kernel = 1; pe.exclude_hv = 1;
            return (int)syscall(__NR_perf_event_open, &pe, 0, -1, -1, 0);
        };
        fds[0]=open_ev(PERF_COUNT_HW_CPU_CYCLES);
        fds[1]=open_ev(PERF_COUNT_HW_INSTRUCTIONS);
        fds[2]=open_ev(PERF_COUNT_HW_CACHE_MISSES);
        fds[3]=open_ev(PERF_COUNT_HW_CACHE_REFERENCES);
        fds[4]=open_ev(PERF_COUNT_HW_BRANCH_MISSES);
        fds[5]=open_ev(PERF_COUNT_HW_BRANCH_INSTRUCTIONS);
        for (int i=0;i<6;++i) if(fds[i]>=0){ioctl(fds[i],PERF_EVENT_IOC_RESET,0);ioctl(fds[i],PERF_EVENT_IOC_ENABLE,0);}
    }
    void stop() {
        for (int i=0;i<6;++i) if(fds[i]>=0) ioctl(fds[i],PERF_EVENT_IOC_DISABLE,0);
        long long v[6]={};
        for (int i=0;i<6;++i) if(fds[i]>=0){::read(fds[i],&v[i],sizeof(long long));close(fds[i]);fds[i]=-1;}
        cycles=v[0]; instructions=v[1]; cache_misses=v[2]; cache_refs=v[3]; branch_misses=v[4]; branches=v[5];
    }
#else
    void start() {}
    void stop() {}
#endif
};

// Reference: pi(10^7) = 664579
static int ReferencePrimeCount(int limit) {
    std::vector<bool> is_prime(limit + 1, true);
    is_prime[0] = is_prime[1] = false;
    for (int i = 2; (long long)i * i <= limit; ++i) {
        if (is_prime[i]) {
            for (int j = i * i; j <= limit; j += i)
                is_prime[j] = false;
        }
    }
    int count = 0;
    for (int i = 2; i <= limit; ++i)
        if (is_prime[i]) ++count;
    return count;
}

// EVOLVE-BLOCK-START

static int CountPrimes(int limit) {
    // Naive sieve: one byte per element, no segmentation, no wheel
    std::vector<uint8_t> sieve(limit + 1, 1);
    sieve[0] = sieve[1] = 0;
    for (int i = 2; (long long)i * i <= limit; ++i) {
        if (sieve[i]) {
            for (int j = i * i; j <= limit; j += i) {
                sieve[j] = 0;
            }
        }
    }
    int count = 0;
    for (int i = 2; i <= limit; ++i) {
        count += sieve[i];
    }
    return count;
}

// EVOLVE-BLOCK-END

static void WriteJson(const std::string &path, const std::string &payload) {
    if (path.empty()) { std::cout << payload << std::endl; return; }
    std::ofstream out(path.c_str(), std::ios::binary);
    out << payload;
}

int main(int argc, char **argv) {
    std::string json_path;
    int limit = 10000000;  // 10^7
    int rounds = 10;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json" && i + 1 < argc) json_path = argv[++i];
        else if (arg == "--limit" && i + 1 < argc) limit = std::atoi(argv[++i]);
        else if (arg == "--rounds" && i + 1 < argc) rounds = std::atoi(argv[++i]);
    }

    // Correctness check
    int ref_count = ReferencePrimeCount(limit);
    int got_count = CountPrimes(limit);
    if (ref_count != got_count) {
        std::cerr << "prime count mismatch: expected " << ref_count
                  << " got " << got_count << std::endl;
        return 2;
    }

    // Benchmark with hardware counters
    HWCounters hwc;
    std::vector<double> latencies;
    latencies.reserve(rounds);
    double total_time = 0.0;

    hwc.start();
    for (int r = 0; r < rounds; ++r) {
        auto t0 = std::chrono::high_resolution_clock::now();
        CountPrimes(limit);
        auto t1 = std::chrono::high_resolution_clock::now();
        double dt = std::chrono::duration<double>(t1 - t0).count();
        latencies.push_back(dt);
        total_time += dt;
    }
    hwc.stop();

    double ops_per_sec = rounds / total_time;
    std::sort(latencies.begin(), latencies.end());
    double p99 = latencies.empty() ? 0.0
        : latencies[(size_t)(0.99 * (latencies.size() - 1))];

    std::ostringstream os;
    os.setf(std::ios::fixed);
    os.precision(6);
    os << "{\"ops_per_sec\":" << ops_per_sec
       << ",\"p99_latency_us\":" << (p99 * 1e6)
       << ",\"prime_count\":" << got_count
       << ",\"hw_cycles\":" << hwc.cycles
       << ",\"hw_instructions\":" << hwc.instructions
       << ",\"hw_cache_misses\":" << hwc.cache_misses
       << ",\"hw_cache_refs\":" << hwc.cache_refs
       << ",\"hw_branch_misses\":" << hwc.branch_misses
       << ",\"hw_branches\":" << hwc.branches << "}";
    WriteJson(json_path, os.str());
    return 0;
}
