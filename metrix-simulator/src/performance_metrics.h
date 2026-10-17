// SPDX-License-Identifier: MPL-2.0

#ifndef METRIX_PERFORMANCE_METRICS_H
#define METRIX_PERFORMANCE_METRICS_H

#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace performance
{
using Clock = std::chrono::steady_clock;

struct Timing {
    unsigned long long calls = 0;
    double milliseconds = 0.0;
};

struct Variant {
    explicit Variant(int n) : number(n) {}

    int number;
    double milliseconds = 0.0;
    std::map<std::string, Timing> phases;
    std::map<std::string, unsigned long long> counters;
};

struct Metrics {
    std::map<std::string, Timing> phases;
    std::map<std::string, unsigned long long> counters;
    std::vector<Variant> variants;
    std::size_t currentVariant = std::numeric_limits<std::size_t>::max();
};

inline bool enabled()
{
    static const bool value = [] {
        const char* flag = std::getenv("METRIX_PERF");
        return flag != nullptr && flag[0] == '1' && flag[1] == '\0';
    }();
    return value;
}

inline Metrics& metrics()
{
    static Metrics value;
    return value;
}

inline bool hasCurrentVariant(const Metrics& value)
{
    return value.currentVariant < value.variants.size();
}

inline void add(const char* name, unsigned long long amount = 1)
{
    if (!enabled()) {
        return;
    }
    Metrics& value = metrics();
    value.counters[name] += amount;
    if (hasCurrentVariant(value)) {
        value.variants[value.currentVariant].counters[name] += amount;
    }
}

inline void maximum(const char* name, unsigned long long observed)
{
    if (!enabled()) {
        return;
    }
    Metrics& value = metrics();
    unsigned long long& global = value.counters[name];
    if (observed > global) {
        global = observed;
    }
    if (hasCurrentVariant(value)) {
        unsigned long long& local = value.variants[value.currentVariant].counters[name];
        if (observed > local) {
            local = observed;
        }
    }
}

class Timer
{
public:
    explicit Timer(const char* name) : name_(name), active_(enabled())
    {
        if (active_) {
            start_ = Clock::now();
        }
    }

    ~Timer()
    {
        if (!active_) {
            return;
        }
        const double elapsed = std::chrono::duration<double, std::milli>(Clock::now() - start_).count();
        Metrics& value = metrics();
        Timing& global = value.phases[name_];
        ++global.calls;
        global.milliseconds += elapsed;
        if (hasCurrentVariant(value)) {
            Timing& local = value.variants[value.currentVariant].phases[name_];
            ++local.calls;
            local.milliseconds += elapsed;
        }
    }

    Timer(const Timer&) = delete;
    Timer& operator=(const Timer&) = delete;

private:
    const char* name_;
    bool active_;
    Clock::time_point start_;
};

class VariantTimer
{
public:
    explicit VariantTimer(int number) : active_(enabled())
    {
        if (active_) {
            Metrics& value = metrics();
            value.variants.emplace_back(number);
            value.currentVariant = value.variants.size() - 1;
            start_ = Clock::now();
        }
    }

    ~VariantTimer()
    {
        if (!active_) {
            return;
        }
        Metrics& value = metrics();
        value.variants[value.currentVariant].milliseconds
            = std::chrono::duration<double, std::milli>(Clock::now() - start_).count();
        value.currentVariant = std::numeric_limits<std::size_t>::max();
    }

    VariantTimer(const VariantTimer&) = delete;
    VariantTimer& operator=(const VariantTimer&) = delete;

private:
    bool active_;
    Clock::time_point start_;
};

inline std::string report()
{
    if (!enabled()) {
        return "";
    }
    const Metrics& value = metrics();
    std::ostringstream out;
    out << std::fixed << std::setprecision(3);
    for (const auto& entry : value.phases) {
        out << "METRIX_PERF phase=" << entry.first << " calls=" << entry.second.calls
            << " milliseconds=" << entry.second.milliseconds << '\n';
    }
    for (const auto& entry : value.counters) {
        out << "METRIX_PERF counter=" << entry.first << " value=" << entry.second << '\n';
    }
    for (const Variant& variant : value.variants) {
        out << "METRIX_PERF variant=" << variant.number << " milliseconds=" << variant.milliseconds;
        for (const auto& entry : variant.counters) {
            out << ' ' << entry.first << '=' << entry.second;
        }
        out << '\n';
    }
    return out.str();
}
} // namespace performance

#endif
