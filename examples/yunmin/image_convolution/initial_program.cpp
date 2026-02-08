#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <random>
#include <sstream>
#include <string>
#include <vector>

static const int K = 5;
static const float KERNEL_5x5[K][K] = {
    {1, 4, 6, 4, 1},
    {4, 16, 24, 16, 4},
    {6, 24, 36, 24, 6},
    {4, 16, 24, 16, 4},
    {1, 4, 6, 4, 1},
};

static float KernelSum() {
    float sum = 0.0f;
    for (int y = 0; y < K; ++y) {
        for (int x = 0; x < K; ++x) {
            sum += KERNEL_5x5[y][x];
        }
    }
    return sum;
}

static void ReferenceConvolve(const std::vector<float> &in, std::vector<float> &out, int w, int h) {
    float norm = 1.0f / KernelSum();
    out.assign(w * h, 0.0f);
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            float acc = 0.0f;
            for (int ky = 0; ky < K; ++ky) {
                int iy = std::min(h - 1, std::max(0, y + ky - 2));
                for (int kx = 0; kx < K; ++kx) {
                    int ix = std::min(w - 1, std::max(0, x + kx - 2));
                    acc += in[iy * w + ix] * KERNEL_5x5[ky][kx];
                }
            }
            out[y * w + x] = acc * norm;
        }
    }
}

// EVOLVE-BLOCK-START

static void Convolve5x5(const std::vector<float> &in, std::vector<float> &out, int w, int h) {
    float norm = 1.0f / KernelSum();
    out.assign(w * h, 0.0f);
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            float acc = 0.0f;
            for (int ky = 0; ky < K; ++ky) {
                int iy = std::min(h - 1, std::max(0, y + ky - 2));
                for (int kx = 0; kx < K; ++kx) {
                    int ix = std::min(w - 1, std::max(0, x + kx - 2));
                    acc += in[iy * w + ix] * KERNEL_5x5[ky][kx];
                }
            }
            out[y * w + x] = acc * norm;
        }
    }
}

// EVOLVE-BLOCK-END

static std::vector<float> GenerateImage(int w, int h, int seed) {
    std::mt19937 rng(seed);
    std::uniform_real_distribution<float> dist(0.0f, 1.0f);
    std::vector<float> img(w * h);
    for (int i = 0; i < w * h; ++i) img[i] = dist(rng);
    return img;
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
    int seed = 42;
    int width = 4096;
    int height = 4096;
    int rounds = 2;
    int batch = 1;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json" && i + 1 < argc) json_path = argv[++i];
        else if (arg == "--seed" && i + 1 < argc) seed = std::atoi(argv[++i]);
        else if (arg == "--width" && i + 1 < argc) width = std::atoi(argv[++i]);
        else if (arg == "--height" && i + 1 < argc) height = std::atoi(argv[++i]);
        else if (arg == "--rounds" && i + 1 < argc) rounds = std::atoi(argv[++i]);
        else if (arg == "--batch" && i + 1 < argc) batch = std::atoi(argv[++i]);
    }

    std::vector<float> image = GenerateImage(width, height, seed);
    std::vector<float> ref;
    std::vector<float> out;

    ReferenceConvolve(image, ref, width, height);
    Convolve5x5(image, out, width, height);

    double max_abs_err = 0.0;
    for (size_t i = 0; i < ref.size(); ++i) {
        double err = std::abs(ref[i] - out[i]);
        if (err > max_abs_err) max_abs_err = err;
    }
    if (max_abs_err > 1e-4) {
        std::cerr << "max error too large: " << max_abs_err << std::endl;
        return 2;
    }

    std::vector<double> latencies;
    latencies.reserve(rounds * batch);
    long long total_ops = 0;
    double total_time = 0.0;
    long long total_pixels = 0;

    for (int r = 0; r < rounds; ++r) {
        for (int b = 0; b < batch; ++b) {
            auto t0 = std::chrono::high_resolution_clock::now();
            Convolve5x5(image, out, width, height);
            auto t1 = std::chrono::high_resolution_clock::now();
            std::chrono::duration<double> dt = t1 - t0;
            total_ops += 1;
            total_time += dt.count();
            total_pixels += static_cast<long long>(width) * height;
            latencies.push_back(dt.count());
        }
    }

    if (total_time <= 0) total_time = 1e-9;
    double ops_per_sec = total_ops / total_time;
    double mpix_per_sec = (total_pixels / 1e6) / total_time;
    std::sort(latencies.begin(), latencies.end());
    double p99 = latencies.empty() ? 0.0 : latencies[static_cast<size_t>(0.99 * (latencies.size() - 1))];

    std::ostringstream os;
    os.setf(std::ios::fixed);
    os.precision(6);
    os << "{\"ops_per_sec\":" << ops_per_sec
       << ",\"p99_latency_us\":" << (p99 * 1e6)
       << ",\"mpix_per_sec\":" << mpix_per_sec << "}";
    WriteJson(json_path, os.str());
    return 0;
}
