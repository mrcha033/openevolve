#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <random>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

struct Parsed {
    std::string method;
    std::string path;
    std::string version;
    std::vector<std::pair<std::string, std::string>> headers;
};

static std::string ToLower(const std::string &s) {
    std::string out = s;
    for (char &c : out) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return out;
}

static Parsed ReferenceParse(const std::string &buf) {
    Parsed p;
    size_t pos = buf.find("\r\n");
    if (pos == std::string::npos) throw std::runtime_error("bad request line");
    std::string line = buf.substr(0, pos);
    size_t sp1 = line.find(' ');
    size_t sp2 = line.find(' ', sp1 + 1);
    if (sp1 == std::string::npos || sp2 == std::string::npos) throw std::runtime_error("bad request line");
    p.method = line.substr(0, sp1);
    p.path = line.substr(sp1 + 1, sp2 - sp1 - 1);
    p.version = line.substr(sp2 + 1);

    size_t i = pos + 2;
    while (i < buf.size()) {
        size_t end = buf.find("\r\n", i);
        if (end == std::string::npos) break;
        if (end == i) break; // empty line
        std::string h = buf.substr(i, end - i);
        size_t colon = h.find(':');
        if (colon == std::string::npos) throw std::runtime_error("bad header");
        std::string name = ToLower(h.substr(0, colon));
        size_t val_start = colon + 1;
        while (val_start < h.size() && h[val_start] == ' ') ++val_start;
        std::string value = h.substr(val_start);
        p.headers.emplace_back(std::move(name), std::move(value));
        i = end + 2;
    }
    return p;
}

static std::string Canonicalize(const Parsed &p) {
    std::vector<std::pair<std::string, std::string>> headers = p.headers;
    std::sort(headers.begin(), headers.end());
    std::string out;
    out.reserve(128);
    out.append(p.method);
    out.push_back('|');
    out.append(p.path);
    out.push_back('|');
    out.append(p.version);
    for (const auto &kv : headers) {
        out.push_back('|');
        out.append(kv.first);
        out.push_back('=');
        out.append(kv.second);
    }
    return out;
}

// EVOLVE-BLOCK-START

static std::string ParseRequestCanonical(const std::string &buf) {
    Parsed p = ReferenceParse(buf);
    return Canonicalize(p);
}

// EVOLVE-BLOCK-END

static std::string MakeRequest(std::mt19937 &rng) {
    static const char *methods[] = {"GET", "POST", "PUT", "DELETE"};
    static const char *header_names[] = {
        "host", "user-agent", "accept", "accept-encoding", "accept-language",
        "cache-control", "connection", "content-type", "x-request-id", "x-forwarded-for"};

    std::uniform_int_distribution<int> method_dist(0, 3);
    std::uniform_int_distribution<int> id_dist(1, 1000);
    std::uniform_int_distribution<int> header_dist(0, 9);
    std::uniform_int_distribution<int> count_dist(6, 10);

    std::string method = methods[method_dist(rng)];
    std::string path = "/api/" + std::to_string(id_dist(rng)) + "/items";
    std::string version = "HTTP/1.1";

    std::vector<std::pair<std::string, std::string>> headers;
    int count = count_dist(rng);
    headers.reserve(count);

    for (int i = 0; i < count; ++i) {
        std::string name = header_names[header_dist(rng)];
        std::string value;
        if (name == "host") value = "service.local";
        else if (name == "user-agent") value = "bench/1.0";
        else if (name == "accept") value = "*/*";
        else if (name == "accept-encoding") value = "gzip, deflate";
        else if (name == "connection") value = "keep-alive";
        else if (name == "content-type") value = "application/json";
        else if (name == "x-request-id") value = std::to_string(100000 + (rng() % 900000));
        else if (name == "x-forwarded-for") value = "192.168.0." + std::to_string(1 + (rng() % 250));
        else value = "no-cache";
        headers.emplace_back(std::move(name), std::move(value));
    }

    std::ostringstream os;
    os << method << " " << path << " " << version << "\r\n";
    for (const auto &kv : headers) {
        os << kv.first << ": " << kv.second << "\r\n";
    }
    os << "\r\n";
    return os.str();
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
    int seed = 2027;
    int count = 5000;
    int rounds = 3;
    int batch = 100;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json" && i + 1 < argc) json_path = argv[++i];
        else if (arg == "--seed" && i + 1 < argc) seed = std::atoi(argv[++i]);
        else if (arg == "--count" && i + 1 < argc) count = std::atoi(argv[++i]);
        else if (arg == "--rounds" && i + 1 < argc) rounds = std::atoi(argv[++i]);
        else if (arg == "--batch" && i + 1 < argc) batch = std::atoi(argv[++i]);
    }

    std::mt19937 rng(seed);
    std::vector<std::string> inputs;
    std::vector<std::string> refs;
    inputs.reserve(count);
    refs.reserve(count);

    for (int i = 0; i < count; ++i) {
        std::string req = MakeRequest(rng);
        inputs.push_back(req);
        refs.push_back(Canonicalize(ReferenceParse(req)));
    }

    for (int i = 0; i < count; ++i) {
        std::string out = ParseRequestCanonical(inputs[i]);
        if (out != refs[i]) {
            std::cerr << "parse mismatch" << std::endl;
            return 2;
        }
    }

    std::vector<double> latencies;
    latencies.reserve((count / batch + 1) * rounds);
    long long total_ops = 0;
    double total_time = 0.0;

    for (int r = 0; r < rounds; ++r) {
        for (int i = 0; i < count; i += batch) {
            int end = std::min(count, i + batch);
            auto t0 = std::chrono::high_resolution_clock::now();
            for (int j = i; j < end; ++j) {
                ParseRequestCanonical(inputs[j]);
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
