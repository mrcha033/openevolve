#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <random>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

struct JValue {
    enum class Type { Null, Bool, Int, String, Array, Object } type;
    bool b = false;
    long long i = 0;
    std::string s;
    std::vector<JValue> arr;
    std::vector<std::pair<std::string, JValue>> obj;
};

static void SkipWs(const std::string &in, size_t &i) {
    while (i < in.size() && std::isspace(static_cast<unsigned char>(in[i]))) {
        ++i;
    }
}

static JValue ParseValue(const std::string &in, size_t &i);

static JValue ParseString(const std::string &in, size_t &i) {
    // in[i] == '"'
    ++i;
    size_t start = i;
    while (i < in.size() && in[i] != '"') {
        ++i;
    }
    if (i >= in.size()) {
        throw std::runtime_error("unterminated string");
    }
    JValue v;
    v.type = JValue::Type::String;
    v.s = in.substr(start, i - start);
    ++i;
    return v;
}

static JValue ParseNumber(const std::string &in, size_t &i) {
    size_t start = i;
    if (in[i] == '-') {
        ++i;
    }
    while (i < in.size() && std::isdigit(static_cast<unsigned char>(in[i]))) {
        ++i;
    }
    if (i == start || (i == start + 1 && in[start] == '-')) {
        throw std::runtime_error("invalid number");
    }
    JValue v;
    v.type = JValue::Type::Int;
    v.i = std::stoll(in.substr(start, i - start));
    return v;
}

static JValue ParseArray(const std::string &in, size_t &i) {
    ++i; // skip '['
    JValue v;
    v.type = JValue::Type::Array;
    SkipWs(in, i);
    if (i < in.size() && in[i] == ']') {
        ++i;
        return v;
    }
    while (true) {
        SkipWs(in, i);
        v.arr.push_back(ParseValue(in, i));
        SkipWs(in, i);
        if (i >= in.size()) {
            throw std::runtime_error("unterminated array");
        }
        if (in[i] == ']') {
            ++i;
            return v;
        }
        if (in[i] != ',') {
            throw std::runtime_error("expected ',' in array");
        }
        ++i;
    }
}

static JValue ParseObject(const std::string &in, size_t &i) {
    ++i; // skip '{'
    JValue v;
    v.type = JValue::Type::Object;
    SkipWs(in, i);
    if (i < in.size() && in[i] == '}') {
        ++i;
        return v;
    }
    while (true) {
        SkipWs(in, i);
        if (i >= in.size() || in[i] != '"') {
            throw std::runtime_error("expected string key");
        }
        JValue key = ParseString(in, i);
        SkipWs(in, i);
        if (i >= in.size() || in[i] != ':') {
            throw std::runtime_error("expected ':' in object");
        }
        ++i;
        SkipWs(in, i);
        JValue val = ParseValue(in, i);
        v.obj.emplace_back(key.s, std::move(val));
        SkipWs(in, i);
        if (i >= in.size()) {
            throw std::runtime_error("unterminated object");
        }
        if (in[i] == '}') {
            ++i;
            return v;
        }
        if (in[i] != ',') {
            throw std::runtime_error("expected ',' in object");
        }
        ++i;
    }
}

static JValue ParseValue(const std::string &in, size_t &i) {
    SkipWs(in, i);
    if (i >= in.size()) {
        throw std::runtime_error("unexpected end");
    }
    char ch = in[i];
    if (ch == '"') {
        return ParseString(in, i);
    }
    if (ch == '{') {
        return ParseObject(in, i);
    }
    if (ch == '[') {
        return ParseArray(in, i);
    }
    if (ch == 't' && in.compare(i, 4, "true") == 0) {
        i += 4;
        JValue v;
        v.type = JValue::Type::Bool;
        v.b = true;
        return v;
    }
    if (ch == 'f' && in.compare(i, 5, "false") == 0) {
        i += 5;
        JValue v;
        v.type = JValue::Type::Bool;
        v.b = false;
        return v;
    }
    if (ch == 'n' && in.compare(i, 4, "null") == 0) {
        i += 4;
        JValue v;
        v.type = JValue::Type::Null;
        return v;
    }
    if (ch == '-' || std::isdigit(static_cast<unsigned char>(ch))) {
        return ParseNumber(in, i);
    }
    throw std::runtime_error("unexpected char");
}

static std::string SerializeValue(const JValue &v) {
    std::string out;
    out.reserve(64);
    std::vector<const JValue *> stack;
    std::vector<size_t> index_stack;

    // Simple recursive serializer for readability in reference.
    std::function<void(const JValue &)> emit = [&](const JValue &val) {
        switch (val.type) {
            case JValue::Type::Null:
                out += "null";
                break;
            case JValue::Type::Bool:
                out += (val.b ? "true" : "false");
                break;
            case JValue::Type::Int:
                out += std::to_string(val.i);
                break;
            case JValue::Type::String:
                out.push_back('"');
                out += val.s;
                out.push_back('"');
                break;
            case JValue::Type::Array: {
                out.push_back('[');
                for (size_t i = 0; i < val.arr.size(); ++i) {
                    if (i > 0) out.push_back(',');
                    emit(val.arr[i]);
                }
                out.push_back(']');
                break;
            }
            case JValue::Type::Object: {
                out.push_back('{');
                for (size_t i = 0; i < val.obj.size(); ++i) {
                    if (i > 0) out.push_back(',');
                    out.push_back('"');
                    out += val.obj[i].first;
                    out.push_back('"');
                    out.push_back(':');
                    emit(val.obj[i].second);
                }
                out.push_back('}');
                break;
            }
        }
    };

    emit(v);
    return out;
}

static std::string ReferenceNormalize(const std::string &in) {
    size_t i = 0;
    JValue v = ParseValue(in, i);
    SkipWs(in, i);
    if (i != in.size()) {
        throw std::runtime_error("trailing characters");
    }
    return SerializeValue(v);
}

// EVOLVE-BLOCK-START

static std::string ParseAndSerialize(const std::string &in) {
    return ReferenceNormalize(in);
}

// EVOLVE-BLOCK-END

static std::string RandomString(std::mt19937 &rng, int min_len, int max_len) {
    std::uniform_int_distribution<int> len_dist(min_len, max_len);
    std::uniform_int_distribution<int> ch_dist(0, 61);
    int n = len_dist(rng);
    std::string out;
    out.reserve(n);
    for (int i = 0; i < n; ++i) {
        int v = ch_dist(rng);
        if (v < 10) out.push_back(static_cast<char>('0' + v));
        else if (v < 36) out.push_back(static_cast<char>('a' + (v - 10)));
        else out.push_back(static_cast<char>('A' + (v - 36)));
    }
    return out;
}

static JValue RandomValue(std::mt19937 &rng, int depth) {
    std::uniform_int_distribution<int> choice_dist(0, depth > 0 ? 4 : 2);
    int choice = choice_dist(rng);
    if (choice == 0) {
        std::uniform_int_distribution<int> num_dist(-100000, 100000);
        JValue v;
        v.type = JValue::Type::Int;
        v.i = num_dist(rng);
        return v;
    }
    if (choice == 1) {
        JValue v;
        v.type = JValue::Type::String;
        v.s = RandomString(rng, 4, 20);
        return v;
    }
    if (choice == 2) {
        JValue v;
        v.type = JValue::Type::Bool;
        v.b = (rng() & 1) != 0;
        return v;
    }
    if (choice == 3) {
        JValue v;
        v.type = JValue::Type::Array;
        std::uniform_int_distribution<int> len_dist(0, 5);
        int n = len_dist(rng);
        v.arr.reserve(n);
        for (int i = 0; i < n; ++i) {
            v.arr.push_back(RandomValue(rng, depth - 1));
        }
        return v;
    }
    JValue v;
    v.type = JValue::Type::Object;
    std::uniform_int_distribution<int> len_dist(0, 5);
    int n = len_dist(rng);
    v.obj.reserve(n);
    for (int i = 0; i < n; ++i) {
        v.obj.emplace_back(RandomString(rng, 3, 10), RandomValue(rng, depth - 1));
    }
    return v;
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
    int seed = 1337;
    int count = 2000;
    int rounds = 3;
    int batch = 50;

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
        JValue v = RandomValue(rng, 3);
        std::string s = SerializeValue(v);
        inputs.push_back(s);
        refs.push_back(ReferenceNormalize(s));
    }

    // Verify correctness once
    for (int i = 0; i < count; ++i) {
        std::string out = ParseAndSerialize(inputs[i]);
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
                ParseAndSerialize(inputs[j]);
            }
            auto t1 = std::chrono::high_resolution_clock::now();
            std::chrono::duration<double> dt = t1 - t0;
            int batch_size = end - i;
            total_ops += batch_size;
            total_time += dt.count();
            if (batch_size > 0) {
                latencies.push_back(dt.count() / batch_size);
            }
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
