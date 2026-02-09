#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <random>
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

// Array-of-Structures layout (deliberately naive for cache performance)
struct Body {
    double x, y, z;
    double vx, vy, vz;
    double mass;
};

// Reference implementation (outside EVOLVE-BLOCK, used for correctness check)
static void ReferenceForces(const std::vector<Body> &bodies,
                            std::vector<double> &fx,
                            std::vector<double> &fy,
                            std::vector<double> &fz) {
    int n = (int)bodies.size();
    fx.assign(n, 0.0);
    fy.assign(n, 0.0);
    fz.assign(n, 0.0);
    const double eps2 = 1e-9;
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            double dx = bodies[j].x - bodies[i].x;
            double dy = bodies[j].y - bodies[i].y;
            double dz = bodies[j].z - bodies[i].z;
            double r2 = dx * dx + dy * dy + dz * dz + eps2;
            double inv_r = 1.0 / std::sqrt(r2);
            double inv_r3 = inv_r * inv_r * inv_r;
            double fi = bodies[j].mass * inv_r3;
            double fj = bodies[i].mass * inv_r3;
            fx[i] += dx * fi; fy[i] += dy * fi; fz[i] += dz * fi;
            fx[j] -= dx * fj; fy[j] -= dy * fj; fz[j] -= dz * fj;
        }
    }
}

// EVOLVE-BLOCK-START

static void ComputeForces(const std::vector<Body> &bodies,
                          std::vector<double> &fx,
                          std::vector<double> &fy,
                          std::vector<double> &fz) {
    int n = (int)bodies.size();
    fx.assign(n, 0.0);
    fy.assign(n, 0.0);
    fz.assign(n, 0.0);
    const double eps2 = 1e-9;
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            double dx = bodies[j].x - bodies[i].x;
            double dy = bodies[j].y - bodies[i].y;
            double dz = bodies[j].z - bodies[i].z;
            double r2 = dx * dx + dy * dy + dz * dz + eps2;
            double inv_r = 1.0 / std::sqrt(r2);
            double inv_r3 = inv_r * inv_r * inv_r;
            double fi = bodies[j].mass * inv_r3;
            double fj = bodies[i].mass * inv_r3;
            fx[i] += dx * fi; fy[i] += dy * fi; fz[i] += dz * fi;
            fx[j] -= dx * fj; fy[j] -= dy * fj; fz[j] -= dz * fj;
        }
    }
}

// EVOLVE-BLOCK-END

static std::vector<Body> GenerateBodies(std::mt19937 &rng, int n) {
    std::uniform_real_distribution<double> pos(-100.0, 100.0);
    std::uniform_real_distribution<double> vel(-1.0, 1.0);
    std::uniform_real_distribution<double> m(0.1, 10.0);
    std::vector<Body> bodies(n);
    for (int i = 0; i < n; ++i) {
        bodies[i] = {pos(rng), pos(rng), pos(rng),
                     vel(rng), vel(rng), vel(rng), m(rng)};
    }
    return bodies;
}

static void WriteJson(const std::string &path, const std::string &payload) {
    if (path.empty()) { std::cout << payload << std::endl; return; }
    std::ofstream out(path.c_str(), std::ios::binary);
    out << payload;
}

int main(int argc, char **argv) {
    std::string json_path;
    int seed = 42;
    int num_bodies = 1024;
    int rounds = 20;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json" && i + 1 < argc) json_path = argv[++i];
        else if (arg == "--seed" && i + 1 < argc) seed = std::atoi(argv[++i]);
        else if (arg == "--bodies" && i + 1 < argc) num_bodies = std::atoi(argv[++i]);
        else if (arg == "--rounds" && i + 1 < argc) rounds = std::atoi(argv[++i]);
    }

    std::mt19937 rng(seed);
    auto bodies = GenerateBodies(rng, num_bodies);

    // Correctness check
    std::vector<double> ref_fx, ref_fy, ref_fz;
    std::vector<double> fx, fy, fz;
    ReferenceForces(bodies, ref_fx, ref_fy, ref_fz);
    ComputeForces(bodies, fx, fy, fz);
    for (int i = 0; i < num_bodies; ++i) {
        double mag = std::abs(ref_fx[i]) + std::abs(ref_fy[i]) + std::abs(ref_fz[i]);
        double err = std::abs(fx[i] - ref_fx[i]) + std::abs(fy[i] - ref_fy[i])
                   + std::abs(fz[i] - ref_fz[i]);
        double tol = std::max(1e-6, mag * 1e-6);
        if (err > tol) {
            std::cerr << "force mismatch at body " << i
                      << " err=" << err << " tol=" << tol << std::endl;
            return 2;
        }
    }

    // Benchmark with hardware counters
    HWCounters hwc;
    std::vector<double> latencies;
    latencies.reserve(rounds);
    double total_time = 0.0;

    hwc.start();
    for (int r = 0; r < rounds; ++r) {
        auto t0 = std::chrono::high_resolution_clock::now();
        ComputeForces(bodies, fx, fy, fz);
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
       << ",\"num_bodies\":" << num_bodies
       << ",\"hw_cycles\":" << hwc.cycles
       << ",\"hw_instructions\":" << hwc.instructions
       << ",\"hw_cache_misses\":" << hwc.cache_misses
       << ",\"hw_cache_refs\":" << hwc.cache_refs
       << ",\"hw_branch_misses\":" << hwc.branch_misses
       << ",\"hw_branches\":" << hwc.branches << "}";
    WriteJson(json_path, os.str());
    return 0;
}
