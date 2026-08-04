/* Offline self-test: byte-for-byte parity with the Python reference tests.
 *
 * Mirrors tests/test_protocol.py and the offline parts of
 * tests/test_config_vehicle.py. No network, no vehicle movement. Exit code 0
 * means every assertion passed.
 *
 * The expected byte strings come directly from the Python gold implementation:
 *   test_workbook_forward_vector: 88 0D EE 01 00 00 00 00 64 FF FF FF 9C
 */

#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "ykcan/config.hpp"
#include "ykcan/json.hpp"
#include "ykcan/protocol.hpp"

namespace {

int g_failures = 0;

/* config.example.json lives in the project root; allow running the selftest
 * from the root or from the CMake build directory. */
std::string find_config_path() {
    if (std::ifstream("config.example.json")) return "config.example.json";
    if (std::ifstream("../config.example.json")) return "../config.example.json";
    return "config.example.json";  /* let from_json produce a clear error */
}

#define CHECK(cond)                                                       \
    do {                                                                  \
        if (!(cond)) {                                                    \
            ++g_failures;                                                 \
            std::cerr << "FAIL: " << #cond << "  (line " << __LINE__ << ")\n"; \
        }                                                                 \
    } while (0)

#define CHECK_THROWS(expr)                                                \
    do {                                                                  \
        bool threw = false;                                               \
        try {                                                             \
            (void)(expr);                                                 \
        } catch (const std::exception&) {                                 \
            threw = true;                                                 \
        }                                                                 \
        if (!threw) {                                                     \
            ++g_failures;                                                 \
            std::cerr << "FAIL: expected exception: " << #expr << "  (line " \
                      << __LINE__ << ")\n";                               \
        }                                                                 \
    } while (0)

std::string bytes_str(const std::array<uint8_t, yk_can::kGatewayFrameSize>& p) {
    return yk_can::format_hex(p.data(), p.size(), true);
}

std::array<uint8_t, 8> i32_pair_payload(int32_t a, int32_t b) {
    std::array<uint8_t, 8> out{};
    yk_can::write_be_i32(out.data(), a);
    yk_can::write_be_i32(out.data() + 4, b);
    return out;
}

void test_protocol() {
    using namespace yk_can;

    /* 1. workbook forward vector: logical M1=+100, M2=-100, driver 1. */
    {
        CanFrame frame = build_motor_frame(1, 100, -100);
        CHECK(bytes_str(frame.to_gateway_bytes()) == "88 0D EE 01 00 00 00 00 64 FF FF FF 9C");
    }
    /* 2. signed motor vector, driver 2. */
    {
        CanFrame frame = build_motor_frame(2, -200, 200);
        CHECK(bytes_str(frame.to_gateway_bytes()) == "88 0D EE 02 00 FF FF FF 38 00 00 00 C8");
    }
    /* 3. parameter write and forbidden registers. */
    {
        CanFrame frame = build_parameter_write_frame(1, 0x0028, 2);
        CHECK(bytes_str(frame.to_gateway_bytes()) == "88 0D EE 01 0A 83 00 28 00 00 02 00 00");
        CHECK_THROWS(build_parameter_write_frame(1, 0x0026, 1));
        CHECK_THROWS(build_parameter_write_frame(1, 0x0027, 1));
    }
    /* 4. fragmented / coalesced / resynchronized stream. */
    {
        CanFrame one = CanFrame::make(yk_can_id(1, 0x01), i32_pair_payload(10, -10), 8);
        CanFrame two = CanFrame::make(yk_can_id(2, 0x01), i32_pair_payload(20, -20), 8);
        std::array<uint8_t, kGatewayFrameSize> one_bytes = one.to_gateway_bytes();
        std::array<uint8_t, kGatewayFrameSize> two_bytes = two.to_gateway_bytes();
        const char noise[] = "noise";
        CanStreamParser parser;
        std::vector<uint8_t> stream;
        stream.insert(stream.end(), noise, noise + 5);
        stream.insert(stream.end(), one_bytes.begin(), one_bytes.begin() + 5);
        CHECK(parser.feed(stream.data(), stream.size()).empty());
        std::vector<uint8_t> stream2;
        stream2.insert(stream2.end(), one_bytes.begin() + 5, one_bytes.end());
        stream2.insert(stream2.end(), two_bytes.begin(), two_bytes.end());
        std::vector<CanFrame> frames = parser.feed(stream2.data(), stream2.size());
        CHECK(frames.size() == 2);
        if (frames.size() == 2) {
            CHECK(frames[0].driver_id().has_value() && *frames[0].driver_id() == 1);
            CHECK(frames[1].driver_id().has_value() && *frames[1].driver_id() == 2);
        }
        CHECK(parser.discarded_bytes() == 5);
    }
    /* 5. speed feedback decode. */
    {
        CanFrame frame = CanFrame::make(yk_can_id(1, 0x01), i32_pair_payload(-50, 75), 8);
        DecodedFeedback fb = decode_feedback(frame, 12.5);
        const SpeedFeedback* s = std::get_if<SpeedFeedback>(&fb);
        CHECK(s != nullptr);
        if (s) {
            CHECK(s->motor1 == -50);
            CHECK(s->motor2 == 75);
            CHECK(s->meta.received_monotonic == 12.5);
        }
    }
    /* 6. thermal fault feedback: 45.5/46.0 C, faults Stall | HallAbnormal. */
    {
        std::array<uint8_t, 8> payload{};
        payload[0] = 0x01;  // 455 >> 8
        payload[1] = 0xC7;  // 455 & 0xFF
        payload[2] = 0x01;
        payload[3] = 0xCC;  // 460
        payload[4] = 0x00;
        payload[5] = 0x60;  // Stall | HallAbnormal
        payload[6] = 0x00;
        payload[7] = 0x00;
        CanFrame frame = CanFrame::make(yk_can_id(2, 0x03), payload, 8);
        DecodedFeedback fb = decode_feedback(frame, 0.0);
        const ThermalFaultFeedback* tf = std::get_if<ThermalFaultFeedback>(&fb);
        CHECK(tf != nullptr);
        if (tf) {
            CHECK(tf->motor1_temperature_c == 45.5);
            CHECK(tf->motor2_temperature_c == 46.0);
            CHECK(tf->has_fault());
            std::vector<std::string> labels = fault_labels_zh(tf->motor1_faults);
            bool found_stall = false;
            for (const std::string& l : labels) {
                if (l == "堵转") found_stall = true;
            }
            CHECK(found_stall);
        }
    }
    /* 7. parameter ack decode: 83 00 28 00 00 02 00 00. */
    {
        const uint8_t raw[8] = {0x83, 0x00, 0x28, 0x00, 0x00, 0x02, 0x00, 0x00};
        CanFrame frame = CanFrame::make(yk_can_id(1, 0x0B), raw, 8);
        DecodedFeedback fb = decode_feedback(frame, 0.0);
        const ParameterAck* ack = std::get_if<ParameterAck>(&fb);
        CHECK(ack != nullptr);
        if (ack) {
            CHECK(ack->reg == 0x0028);
            CHECK(ack->value == 2);
        }
    }
    /* 8. electrical feedback decode: raw 100/200/300 -> 10.0/20.0/30.0. */
    {
        std::array<uint8_t, 8> payload{};
        payload[0] = 0x00; payload[1] = 100;
        payload[2] = 0x00; payload[3] = 200;
        payload[4] = 0x00; payload[5] = 300;
        payload[6] = 0xAB; payload[7] = 0xCD;
        CanFrame frame = CanFrame::make(yk_can_id(1, 0x02), payload, 8);
        DecodedFeedback fb = decode_feedback(frame, 0.0);
        const ElectricalFeedback* e = std::get_if<ElectricalFeedback>(&fb);
        CHECK(e != nullptr);
        if (e) {
            CHECK(e->motor1_current_a == 10.0);
            CHECK(e->motor2_current_a == 20.0);
            CHECK(e->supply_voltage_v == 30.0);
            CHECK(e->tail[0] == 0xAB && e->tail[1] == 0xCD);
        }
    }
    /* 9. invalid frames are rejected. */
    {
        CHECK_THROWS(CanFrame::make(0x7FF + 1, static_cast<const uint8_t*>(nullptr), 0, false));
        std::array<uint8_t, kGatewayFrameSize> bad{};
        bad[0] = 0x88;
        bad[1] = 0x00; bad[2] = 0x01; bad[3] = 0x00; bad[4] = 0x00;  /* not 0x0DEE */
        CHECK_THROWS(CanFrame::from_gateway_bytes(bad, true));
    }
}

void test_config() {
    using namespace yk_can;

    NetworkConfig net;
    CHECK(net.host == "192.168.0.7");
    CHECK(net.port == 5578);

    CHECK_THROWS(SafetyLimits(1101, 0.02, 0.25, 600.0, 1200.0, 10.0, 10, 10, true));
    CHECK_THROWS(SafetyLimits(300, 0.02, 0.5, 600.0, 1200.0, 10.0, 10, 10, true));
    CHECK_THROWS(VehicleConfig(NetworkConfig(), SafetyLimits(), 1, 1, 1, -1, 1, -1));

    VehicleConfig cfg = VehicleConfig::from_json(find_config_path());
    CHECK(cfg.network.host == "192.168.0.7");
    CHECK(cfg.network.port == 5578);
    CHECK(cfg.safety.max_command == 300);
    CHECK(cfg.front_driver_id == 1);
    CHECK(cfg.rear_driver_id == 2);
    CHECK(cfg.front_motor2_sign == -1);
    CHECK(cfg.safety.auto_estop_on_fault == true);

    /* JSON round trip preserves values. */
    json::Value parsed = json::Value::parse(cfg.to_json_string(false));
    CHECK(parsed.find("network") != nullptr);
    const json::Value* port = parsed.find("network")->find("port");
    CHECK(port != nullptr && port->int_or(0) == 5578);

    /* Wrong JSON must raise. */
    CHECK_THROWS(VehicleConfig::from_json_string("{ not json"));
}

}  // namespace

int main(int argc, char** argv) {
    if (argc > 1) {
        std::cerr << "usage: ykcan_selftest [runs from the YK_CANSDK_CPP directory]\n";
        return 2;
    }
    test_protocol();
    test_config();
    if (g_failures == 0) {
        std::cout << "selftest OK: all offline checks passed\n";
        return 0;
    }
    std::cerr << "selftest FAILED with " << g_failures << " failure(s)\n";
    return 1;
}
