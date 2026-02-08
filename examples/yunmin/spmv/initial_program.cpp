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

struct CSR {
    int rows;
    int cols;
    std::vector<int> row_ptr;
    std::vector<int> col_idx;
    std::vector<double> values;
};

static CSR GenerateCSR(int rows, int cols, int nnz_per_row, int seed) {
    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> col_dist(0, cols - 1);
    std::uniform_real_distribution<double> val_dist(-1.0, 1.0);
    CSR m;
    m.rows = rows;
    m.cols = cols;
    m.row_ptr.resize(rows + 1, 0);
    m.col_idx.reserve(static_cast<size_t>(rows) * nnz_per_row);
    m.values.reserve(static_cast<size_t>(rows) * nnz_per_row);

    for (int r = 0; r < rows; ++r) {
        m.row_ptr[r] = static_cast<int>(m.col_idx.size());
        std::vector<int> cols_row;
        cols_row.reserve(nnz_per_row);
        // Always include diagonal for stability
        cols_row.push_back(r % cols);
        while (static_cast<int>(cols_row.size()) < nnz_per_row) {
            cols_row.push_back(col_dist(rng));
        }
        std::sort(cols_row.begin(), cols_row.end());
        for (int c : cols_row) {
            m.col_idx.push_back(c);
            m.values.push_back(val_dist(rng));
        }
    }
    m.row_ptr[rows] = static_cast<int>(m.col_idx.size());
    return m;
}

static void ReferenceSpMV(const CSR &m, const std::vector<double> &x, std::vector<double> &y) {
    y.assign(m.rows, 0.0);
    for (int r = 0; r < m.rows; ++r) {
        double sum = 0.0;
        int start = m.row_ptr[r];
        int end = m.row_ptr[r + 1];
        for (int idx = start; idx < end; ++idx) {
            sum += m.values[idx] * x[m.col_idx[idx]];
        }
        y[r] = sum;
    }
}

// EVOLVE-BLOCK-START

static void SpMV(const CSR &m, const std::vector<double> &x, std::vector<double> &y) {
    y.assign(m.rows, 0.0);
    for (int r = 0; r < m.rows; ++r) {
        double sum = 0.0;
        int start = m.row_ptr[r];
        int end = m.row_ptr[r + 1];
        for (int idx = start; idx < end; ++idx) {
            sum += m.values[idx] * x[m.col_idx[idx]];
        }
        y[r] = sum;
    }
}

// EVOLVE-BLOCK-END

static std::vector<double> GenerateVector(int size, int seed) {
    std::mt19937 rng(seed);
    std::uniform_real_distribution<double> dist(-1.0, 1.0);
    std::vector<double> x(size);
    for (int i = 0; i < size; ++i) x[i] = dist(rng);
    return x;
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
    int rows = 200000;
    int cols = 200000;
    int nnz_per_row = 16;
    int rounds = 3;
    int batch = 1;
    int seed = 123;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json" && i + 1 < argc) json_path = argv[++i];
        else if (arg == "--rows" && i + 1 < argc) rows = std::atoi(argv[++i]);
        else if (arg == "--cols" && i + 1 < argc) cols = std::atoi(argv[++i]);
        else if (arg == "--nnz" && i + 1 < argc) nnz_per_row = std::atoi(argv[++i]);
        else if (arg == "--rounds" && i + 1 < argc) rounds = std::atoi(argv[++i]);
        else if (arg == "--batch" && i + 1 < argc) batch = std::atoi(argv[++i]);
        else if (arg == "--seed" && i + 1 < argc) seed = std::atoi(argv[++i]);
    }

    CSR mat = GenerateCSR(rows, cols, nnz_per_row, seed);
    std::vector<double> x = GenerateVector(cols, seed + 1);
    std::vector<double> ref;
    std::vector<double> out;

    ReferenceSpMV(mat, x, ref);
    SpMV(mat, x, out);

    double max_abs_err = 0.0;
    for (int i = 0; i < rows; ++i) {
        double err = std::abs(ref[i] - out[i]);
        if (err > max_abs_err) max_abs_err = err;
    }
    if (max_abs_err > 1e-9) {
        std::cerr << "max error too large: " << max_abs_err << std::endl;
        return 2;
    }

    std::vector<double> latencies;
    latencies.reserve(rounds * batch);
    long long total_ops = 0;
    double total_time = 0.0;
    long long total_nnz = static_cast<long long>(rows) * nnz_per_row;

    for (int r = 0; r < rounds; ++r) {
        for (int b = 0; b < batch; ++b) {
            auto t0 = std::chrono::high_resolution_clock::now();
            SpMV(mat, x, out);
            auto t1 = std::chrono::high_resolution_clock::now();
            std::chrono::duration<double> dt = t1 - t0;
            total_ops += 1;
            total_time += dt.count();
            latencies.push_back(dt.count());
        }
    }

    if (total_time <= 0) total_time = 1e-9;
    double ops_per_sec = total_ops / total_time;
    double gflops = (2.0 * total_nnz) / (total_time * 1e9);
    std::sort(latencies.begin(), latencies.end());
    double p99 = latencies.empty() ? 0.0 : latencies[static_cast<size_t>(0.99 * (latencies.size() - 1))];

    std::ostringstream os;
    os.setf(std::ios::fixed);
    os.precision(6);
    os << "{\"ops_per_sec\":" << ops_per_sec
       << ",\"p99_latency_us\":" << (p99 * 1e6)
       << ",\"gflops\":" << gflops << "}";
    WriteJson(json_path, os.str());
    return 0;
}
