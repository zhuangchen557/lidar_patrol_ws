#pragma once
/* USR-CAN115 13-byte standard-conversion frame and Yunkang CAN protocol.
 *
 * C++ port of yk_can_sdk/protocol.py. Byte-for-byte identical wire behaviour:
 * frame layout, big-endian integers, ID prefix 0x0DEE, known function codes,
 * feedback decoding and stream re-synchronisation all mirror the Python gold
 * reference implementation.
 */

#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <optional>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace yk_can {

/* Steady monotonic clock in seconds; same role as Python time.monotonic(). */
inline double monotonic_seconds() {
    return std::chrono::duration<double>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

inline constexpr size_t kGatewayFrameSize = 13;
inline constexpr uint32_t kYkCanIdPrefix = 0x0DEEu;
inline constexpr std::array<uint8_t, 10> kKnownFunctions = {
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0A, 0x0B};

class Error : public std::runtime_error {
public:
    explicit Error(const std::string& what) : std::runtime_error(what) {}
};

class ValueError : public Error {
public:
    explicit ValueError(const std::string& what) : Error(what) {}
};

class ConnectionError : public Error {
public:
    explicit ConnectionError(const std::string& what) : Error(what) {}
};

/* ---------- helpers used by several modules ---------- */

inline bool is_known_function(uint8_t fn) {
    for (uint8_t k : kKnownFunctions) {
        if (k == fn) return true;
    }
    return false;
}

inline std::string format_hex(const uint8_t* data, size_t len, bool space_separated = false) {
    static const char* kDigits = "0123456789ABCDEF";
    std::string out;
    out.reserve(len * (space_separated ? 3 : 2));
    for (size_t i = 0; i < len; ++i) {
        out += kDigits[(data[i] >> 4) & 0x0F];
        out += kDigits[data[i] & 0x0F];
        if (space_separated && i + 1 < len) out += ' ';
    }
    return out;
}

inline std::string format_hex(const std::array<uint8_t, 8>& data, uint8_t len, bool space_separated = true) {
    return format_hex(data.data(), len, space_separated);
}

inline uint32_t read_be_u32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | static_cast<uint32_t>(p[3]);
}

inline int32_t read_be_i32(const uint8_t* p) {
    return static_cast<int32_t>(read_be_u32(p));
}

inline int16_t read_be_i16(const uint8_t* p) {
    return static_cast<int16_t>((static_cast<uint16_t>(p[0]) << 8) | static_cast<uint16_t>(p[1]));
}

inline uint16_t read_be_u16(const uint8_t* p) {
    return static_cast<uint16_t>((static_cast<uint16_t>(p[0]) << 8) | static_cast<uint16_t>(p[1]));
}

inline void write_be_u32(uint8_t* p, uint32_t v) {
    p[0] = static_cast<uint8_t>((v >> 24) & 0xFF);
    p[1] = static_cast<uint8_t>((v >> 16) & 0xFF);
    p[2] = static_cast<uint8_t>((v >> 8) & 0xFF);
    p[3] = static_cast<uint8_t>(v & 0xFF);
}

inline void write_be_i32(uint8_t* p, int32_t v) {
    write_be_u32(p, static_cast<uint32_t>(v));
}

/* ---------- fault bits ---------- */

namespace fault {
inline constexpr uint16_t None = 0;
inline constexpr uint16_t Overcurrent = 1u << 0;
inline constexpr uint16_t LoadAbnormal = 1u << 1;
inline constexpr uint16_t Overtemperature = 1u << 2;
inline constexpr uint16_t Overvoltage = 1u << 3;
inline constexpr uint16_t Undervoltage = 1u << 4;
inline constexpr uint16_t Stall = 1u << 5;
inline constexpr uint16_t HallAbnormal = 1u << 6;
inline constexpr uint16_t AbnormalJitter = 1u << 7;
}  // namespace fault

using FaultBits = uint16_t;

/* Labels in the same order as Python Fault.labels_zh; 'self & flag' tests. */
inline std::vector<std::string> fault_labels_zh(FaultBits bits) {
    struct Entry {
        FaultBits bit;
        const char* label;
    };
    static const Entry kMap[] = {
        {fault::Overcurrent, "电流过大"},
        {fault::LoadAbnormal, "负载异常"},
        {fault::Overtemperature, "温度过高"},
        {fault::Overvoltage, "电压过高"},
        {fault::Undervoltage, "电压过低"},
        {fault::Stall, "堵转"},
        {fault::HallAbnormal, "霍尔异常"},
        {fault::AbnormalJitter, "异常抖动"},
    };
    std::vector<std::string> out;
    for (const auto& e : kMap) {
        if (bits & e.bit) out.emplace_back(e.label);
    }
    return out;
}

/* ---------- CAN frame (CAN115 standard-conversion form) ---------- */

inline std::string hex_upper32(uint32_t v) {
    static const char* kDigits = "0123456789ABCDEF";
    std::string out(8, '0');
    for (int i = 7; i >= 0; --i) {
        out[static_cast<size_t>(i)] = kDigits[v & 0x0F];
        v >>= 4;
    }
    return out;
}

inline std::string hex_upper16(uint16_t v) {
    static const char* kDigits = "0123456789ABCDEF";
    std::string out(4, '0');
    for (int i = 3; i >= 0; --i) {
        out[static_cast<size_t>(i)] = kDigits[v & 0x0F];
        v >>= 4;
    }
    return out;
}

struct CanFrame;
inline bool is_plausible_yk_frame(const CanFrame& frame);

struct CanFrame {
    uint32_t can_id = 0;
    std::array<uint8_t, 8> data{};
    uint8_t dlc = 0;
    bool extended = true;
    bool remote = false;

    CanFrame() = default;

    static CanFrame make(uint32_t id, const uint8_t* payload, uint8_t len,
                         bool ext = true, bool rm = false) {
        if (len > 8) throw ValueError("classic CAN payload cannot exceed 8 bytes");
        uint32_t max_id = ext ? 0x1FFFFFFFu : 0x7FFu;
        if (id > max_id) {
            throw ValueError("CAN ID out of range for frame type: 0x" + hex_upper32(id));
        }
        CanFrame f;
        f.can_id = id;
        f.dlc = len;
        f.extended = ext;
        f.remote = rm;
        if (len > 0 && payload != nullptr) {
            std::memcpy(f.data.data(), payload, len);
        }
        return f;
    }

    static CanFrame make(uint32_t id, const std::array<uint8_t, 8>& payload, uint8_t dlc,
                         bool extended = true, bool remote = false) {
        return make(id, payload.data(), dlc, extended, remote);
    }

    /* driver_id: None if the 29-bit ID is not a 0x0DEE frame. */
    std::optional<uint8_t> driver_id() const {
        if ((can_id >> 16) != kYkCanIdPrefix) return std::nullopt;
        return static_cast<uint8_t>((can_id >> 8) & 0xFF);
    }

    std::optional<uint8_t> function() const {
        if (!driver_id().has_value()) return std::nullopt;
        return static_cast<uint8_t>(can_id & 0xFF);
    }

    std::array<uint8_t, kGatewayFrameSize> to_gateway_bytes() const {
        std::array<uint8_t, kGatewayFrameSize> out{};
        uint8_t info = static_cast<uint8_t>((extended ? 0x80 : 0) | (remote ? 0x40 : 0) | dlc);
        out[0] = info;
        write_be_u32(out.data() + 1, can_id);
        std::memcpy(out.data() + 5, data.data(), 8);
        return out;
    }

    static CanFrame from_gateway_bytes(const std::array<uint8_t, kGatewayFrameSize>& packet,
                                       bool require_yk_frame = false) {
        uint8_t info = packet[0];
        if (info & 0x30) throw ValueError("reserved frame-info bits must be zero");
        uint8_t dlc = info & 0x0F;
        if (dlc > 8) throw ValueError("CAN DLC cannot exceed 8");
        CanFrame frame;
        frame.can_id = read_be_u32(packet.data() + 1);
        frame.dlc = dlc;
        frame.extended = (info & 0x80) != 0;
        frame.remote = (info & 0x40) != 0;
        std::memcpy(frame.data.data(), packet.data() + 5, 8);
        if (require_yk_frame && !is_plausible_yk_frame(frame)) {
            throw ValueError("packet is not a plausible Yunkang extended CAN frame");
        }
        return frame;
    }

    std::string to_string() const;
};

inline std::string CanFrame::to_string() const {
    return "CanFrame(can_id=0x" + hex_upper32(can_id) +
           ", data=" + format_hex(data.data(), dlc) +
           ", extended=" + (extended ? "True" : "False") +
           ", remote=" + (remote ? "True" : "False") + ")";
}

inline bool is_plausible_yk_frame(const CanFrame& frame) {
    if (!frame.extended || frame.remote) return false;
    if ((frame.can_id >> 16) != kYkCanIdPrefix) return false;
    auto did = frame.driver_id();
    if (!did.has_value() || *did < 1) return false;
    auto fn = frame.function();
    if (!fn.has_value() || !is_known_function(*fn)) return false;
    return true;
}

/* ---------- resynchronising stream parser ---------- */

class CanStreamParser {
public:
    explicit CanStreamParser(bool yk_frames_only = true) : yk_frames_only_(yk_frames_only) {}

    size_t buffered_bytes() const { return buffer_.size(); }
    uint64_t discarded_bytes() const { return discarded_bytes_; }
    bool yk_frames_only() const { return yk_frames_only_; }

    std::vector<CanFrame> feed(const uint8_t* data, size_t len) {
        buffer_.insert(buffer_.end(), data, data + len);
        std::vector<CanFrame> frames;
        while (buffer_.size() >= kGatewayFrameSize) {
            std::array<uint8_t, kGatewayFrameSize> packet;
            std::memcpy(packet.data(), buffer_.data(), kGatewayFrameSize);
            try {
                CanFrame frame = CanFrame::from_gateway_bytes(packet, yk_frames_only_);
                buffer_.erase(buffer_.begin(), buffer_.begin() + kGatewayFrameSize);
                frames.push_back(std::move(frame));
            } catch (const ValueError&) {
                buffer_.erase(buffer_.begin());
                ++discarded_bytes_;
            }
        }
        return frames;
    }

    void clear() { buffer_.clear(); }

private:
    std::vector<uint8_t> buffer_;
    bool yk_frames_only_;
    uint64_t discarded_bytes_ = 0;
};

/* ---------- frame builders ---------- */

inline uint32_t yk_can_id(uint8_t driver_id, uint8_t function) {
    if (driver_id < 1 || driver_id > 100) throw ValueError("driver_id must be in 1..100");
    return (kYkCanIdPrefix << 16) | (static_cast<uint32_t>(driver_id) << 8) |
           static_cast<uint32_t>(function);
}

inline CanFrame build_motor_frame(uint8_t driver_id, int32_t motor1, int32_t motor2) {
    if (motor1 < INT32_MIN || motor1 > INT32_MAX || motor2 < INT32_MIN || motor2 > INT32_MAX) {
        throw ValueError("motor values must fit a signed 32-bit integer");
    }
    std::array<uint8_t, 8> payload{};
    write_be_i32(payload.data(), motor1);
    write_be_i32(payload.data() + 4, motor2);
    return CanFrame::make(yk_can_id(driver_id, 0x00), payload, 8, true, false);
}

inline CanFrame build_parameter_write_frame(uint8_t driver_id, uint16_t reg, uint16_t value) {
    if (reg == 0x0026 || reg == 0x0027) {
        throw ValueError("registers 0x0026 and 0x0027 are forbidden by the driver manual");
    }
    std::array<uint8_t, 8> payload{};
    payload[0] = 0x83;
    payload[1] = static_cast<uint8_t>((reg >> 8) & 0xFF);
    payload[2] = static_cast<uint8_t>(reg & 0xFF);
    payload[3] = 0x00;
    payload[4] = static_cast<uint8_t>((value >> 8) & 0xFF);
    payload[5] = static_cast<uint8_t>(value & 0xFF);
    payload[6] = 0x00;
    payload[7] = 0x00;
    return CanFrame::make(yk_can_id(driver_id, 0x0A), payload, 8, true, false);
}

/* ---------- feedback types ---------- */

struct FeedbackHeader {
    uint8_t driver_id = 0;
    double received_monotonic = 0.0;
};

struct SpeedFeedback {
    FeedbackHeader meta;
    int32_t motor1 = 0;
    int32_t motor2 = 0;
};

struct ElectricalFeedback {
    FeedbackHeader meta;
    double motor1_current_a = 0.0;
    double motor2_current_a = 0.0;
    double supply_voltage_v = 0.0;
    std::array<uint8_t, 2> tail{};
};

struct ThermalFaultFeedback {
    FeedbackHeader meta;
    double motor1_temperature_c = 0.0;
    double motor2_temperature_c = 0.0;
    FaultBits motor1_faults = 0;
    FaultBits motor2_faults = 0;

    bool has_fault() const { return motor1_faults != 0 || motor2_faults != 0; }
};

struct PositionFeedback {
    FeedbackHeader meta;
    int32_t motor1 = 0;
    int32_t motor2 = 0;
};

struct ParameterAck {
    FeedbackHeader meta;
    uint8_t command = 0;
    uint16_t reg = 0;
    uint16_t value = 0;
    std::array<uint8_t, 3> reserved{};
};

struct RawFeedback {
    FeedbackHeader meta;
    uint8_t function = 0;
    std::array<uint8_t, 8> data{};
    uint8_t dlc = 0;
};

using DecodedFeedback = std::variant<SpeedFeedback, ElectricalFeedback, ThermalFaultFeedback,
                                     PositionFeedback, ParameterAck, RawFeedback>;

inline std::array<uint8_t, 8> require_eight(const CanFrame& frame) {
    if (frame.dlc != 8) {
        throw ValueError("function requires an 8-byte payload");
    }
    return frame.data;
}

inline DecodedFeedback decode_feedback(const CanFrame& frame, double received_monotonic = 0.0) {
    if (!is_plausible_yk_frame(frame)) throw ValueError("not a Yunkang driver frame");
    auto did = frame.driver_id();
    auto fn = frame.function();
    if (!did.has_value() || !fn.has_value()) throw ValueError("not a Yunkang driver frame");

    FeedbackHeader header;
    header.driver_id = *did;
    header.received_monotonic = received_monotonic;

    switch (*fn) {
        case 0x01: {
            std::array<uint8_t, 8> d = require_eight(frame);
            return SpeedFeedback{header, read_be_i32(d.data()), read_be_i32(d.data() + 4)};
        }
        case 0x02: {
            std::array<uint8_t, 8> d = require_eight(frame);
            int16_t c1 = read_be_i16(d.data());
            int16_t c2 = read_be_i16(d.data() + 2);
            int16_t v = read_be_i16(d.data() + 4);
            ElectricalFeedback out;
            out.meta = header;
            out.motor1_current_a = c1 / 10.0;
            out.motor2_current_a = c2 / 10.0;
            out.supply_voltage_v = v / 10.0;
            out.tail = {d[6], d[7]};
            return out;
        }
        case 0x03: {
            std::array<uint8_t, 8> d = require_eight(frame);
            int16_t t1 = read_be_i16(d.data());
            int16_t t2 = read_be_i16(d.data() + 2);
            uint16_t f1 = read_be_u16(d.data() + 4);
            uint16_t f2 = read_be_u16(d.data() + 6);
            ThermalFaultFeedback out;
            out.meta = header;
            out.motor1_temperature_c = t1 / 10.0;
            out.motor2_temperature_c = t2 / 10.0;
            out.motor1_faults = f1;
            out.motor2_faults = f2;
            return out;
        }
        case 0x04: {
            std::array<uint8_t, 8> d = require_eight(frame);
            PositionFeedback out;
            out.meta = header;
            out.motor1 = read_be_i32(d.data());
            out.motor2 = read_be_i32(d.data() + 4);
            return out;
        }
        case 0x0B: {
            std::array<uint8_t, 8> d = require_eight(frame);
            ParameterAck out;
            out.meta = header;
            out.command = d[0];
            out.reg = read_be_u16(d.data() + 1);
            out.value = read_be_u16(d.data() + 4);
            out.reserved = {d[3], d[6], d[7]};
            return out;
        }
        default: {
            RawFeedback out;
            out.meta = header;
            out.function = *fn;
            out.data = frame.data;
            out.dlc = frame.dlc;
            return out;
        }
    }
}

}  // namespace yk_can