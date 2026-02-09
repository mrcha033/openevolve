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

static const int GRID_N = 1024;

// Reference stencil step (outside EVOLVE-BLOCK)
static void ReferenceStep(const std::vector<double> &in,
                          std::vector<double> &out, int N) {
    for (int i = 1; i < N - 1; ++i) {
        for (int j = 1; j < N - 1; ++j) {
            out[i * N + j] = 0.25 * (in[(i - 1) * N + j] + in[(i + 1) * N + j]
                                   + in[i * N + (j - 1)] + in[i * N + (j + 1)]);
        }
    }
}

// EVOLVE-BLOCK-START

static void StencilStep(const std::vector<double> &in,
                        std::vector<double> &out, int N) {
    // 5-point Jacobi stencil: average of 4 neighbors
    // Highly optimized version with minimal overhead and improved cache locality
    const int Nm2 = N - 2;
    
    // Process rows sequentially with optimized loop structure
    for (int i = 1; i <= Nm2; ++i) {
        const int base_i = i * N;
        const int base_im1 = base_i - N;  // (i-1) * N
        const int base_ip1 = base_i + N;  // (i+1) * N
        
        // Unroll inner loop by 4 for better instruction-level parallelism
        int j = 1;
        const int j_end = Nm2 - 3;
        for (; j <= j_end; j += 4) {
            const int base_j = base_i + j;
            
            // Compute four stencil points simultaneously using precomputed offsets
            const double val0 = in[base_im1 + j] + in[base_ip1 + j] +
                               in[base_i + j - 1] + in[base_i + j + 1];
            const double val1 = in[base_im1 + j + 1] + in[base_ip1 + j + 1] +
                               in[base_i + j] + in[base_i + j + 2];
            const double val2 = in[base_im1 + j + 2] + in[base_ip1 + j + 2] +
                               in[base_i + j + 1] + in[base_i + j + 3];
            const double val3 = in[base_im1 + j + 3] + in[base_ip1 + j + 3] +
                               in[base_i + j + 2] + in[base_i + j + 4];
            
            out[base_j] = 0.25 * val0;
            out[base_j + 1] = 0.25 * val1;
            out[base_j + 2] = 0.25 * val2;
            out[base_j + 3] = 0.25 * val3;
        }
        
        // Handle remaining elements
        for (; j <= Nm2; ++j) {
            const int base_j = base_i + j;
            out[base_j] = 0.25 * (in[base_im1 + j] + in[base_ip1 + j] +
                                 in[base_i + j - 1] + in[base_i + j + 1]);
        }
    }
}

// EVOLVE-BLOCK-END

static double GridChecksum(const std::vector<double> &grid, int N) {
    double sum = 0.0;
    for (int i = 0; i < N * N; ++i) sum += grid[i];
    return sum;
}

static void WriteJson(const std::string &path, const std::string &payload) {
    if (path.empty()) { std::cout << payload << std::endl; return; }
    std::ofstream out(path.c_str(), std::ios::binary);
    out << payload;
}

int main(int argc, char **argv) {
    std::string json_path;
    int seed = 42;
    int N = GRID_N;
    int timesteps = 100;
    int rounds = 5;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json" && i + 1 < argc) json_path = argv[++i];
        else if (arg == "--seed" && i + 1 < argc) seed = std::atoi(argv[++i]);
        else if (arg == "--grid" && i + 1 < argc) N = std::atoi(argv[++i]);
        else if (arg == "--timesteps" && i + 1 < argc) timesteps = std::atoi(argv[++i]);
        else if (arg == "--rounds" && i + 1 < argc) rounds = std::atoi(argv[++i]);
    }

    // Initialize grid with deterministic values; boundaries stay 0
    std::mt19937 rng(seed);
    std::uniform_real_distribution<double> dist(0.0, 1.0);
    std::vector<double> grid_a(N * N, 0.0);
    std::vector<double> grid_b(N * N, 0.0);
    for (int i = 1; i < N - 1; ++i)
        for (int j = 1; j < N - 1; ++j)
            grid_a[i * N + j] = dist(rng);

    // Reference grids for correctness check (run 10 steps)
    std::vector<double> ref_a(grid_a), ref_b(N * N, 0.0);
    for (int t = 0; t < 10; ++t) {
        ReferenceStep(ref_a, ref_b, N);
        std::swap(ref_a, ref_b);
    }
    double ref_checksum = GridChecksum(ref_a, N);

    // Evolved function: same 10 steps
    std::vector<double> test_a(grid_a), test_b(N * N, 0.0);
    for (int t = 0; t < 10; ++t) {
        StencilStep(test_a, test_b, N);
        std::swap(test_a, test_b);
    }
    double test_checksum = GridChecksum(test_a, N);

    if (std::abs(ref_checksum - test_checksum) > 1e-6) {
        std::cerr << "stencil mismatch: ref=" << ref_checksum
                  << " got=" << test_checksum << std::endl;
        return 2;
    }

    // Benchmark: each round runs `timesteps` stencil steps
    std::vector<double> latencies;
    latencies.reserve(rounds * timesteps);
    double total_time = 0.0;
    long long total_steps = 0;

    for (int r = 0; r < rounds; ++r) {
        // Re-init grid each round for consistent measurement
        std::copy(grid_a.begin(), grid_a.end(), test_a.begin());
        std::fill(test_b.begin(), test_b.end(), 0.0);

        for (int t = 0; t < timesteps; ++t) {
            auto t0 = std::chrono::high_resolution_clock::now();
            StencilStep(test_a, test_b, N);
            auto t1 = std::chrono::high_resolution_clock::now();
            double dt = std::chrono::duration<double>(t1 - t0).count();
            latencies.push_back(dt);
            total_time += dt;
            ++total_steps;
            std::swap(test_a, test_b);
        }
    }

    double ops_per_sec = total_steps / total_time;
    std::sort(latencies.begin(), latencies.end());
    double p99 = latencies.empty() ? 0.0
        : latencies[(size_t)(0.99 * (latencies.size() - 1))];
    // Each step updates (N-2)*(N-2) cells, 5 FLOP each
    double gflops = (double)(N - 2) * (N - 2) * 5.0 * total_steps
                  / total_time / 1e9;

    std::ostringstream os;
    os.setf(std::ios::fixed);
    os.precision(6);
    os << "{\"ops_per_sec\":" << ops_per_sec
       << ",\"p99_latency_us\":" << (p99 * 1e6)
       << ",\"gflops\":" << gflops
       << ",\"grid_size\":" << N << "}";
    WriteJson(json_path, os.str());
    return 0;
}