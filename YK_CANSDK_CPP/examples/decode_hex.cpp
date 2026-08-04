/* Offline example for decoding one or more 13-byte CAN115 return frames.
 * C++ port of examples/decode_hex.py.
 */

#include <cstdint>
#include <iostream>
#include <string>

#include "ykcan/protocol.hpp"

namespace {
const char* kHexStream = "88 0D EE 01 01 00 00 00 64 FF FF FF 9C";

std::vector<uint8_t> hex_to_bytes(const std::string& hex) {
    std::vector<uint8_t> out;
    for (size_t i = 0; i < hex.size(); ++i) {
        char c = hex[i];
        if (c == ' ' || c == '\n' || c == '\t' || c == '\r') continue;
        unsigned char hi = 0, lo = 0;
        auto nibble = [](char ch) -> int {
            if (ch >= '0' && ch <= '9') return ch - '0';
            if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
            if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
            return -1;
        };
        if (i + 1 >= hex.size()) break;
        hi = static_cast<unsigned char>(nibble(c));
        lo = static_cast<unsigned char>(nibble(hex[i + 1]));
        if (hi > 15 || lo > 15) break;
        out.push_back(static_cast<uint8_t>((hi << 4) | lo));
        ++i;
    }
    return out;
}
}  // namespace

int main() {
    using namespace yk_can;
    std::vector<uint8_t> stream = hex_to_bytes(kHexStream);
    CanStreamParser parser;
    for (const CanFrame& frame : parser.feed(stream.data(), stream.size())) {
        std::cout << frame.to_string() << "\n";
        DecodedFeedback fb = decode_feedback(frame, 0.0);
        const SpeedFeedback* s = std::get_if<SpeedFeedback>(&fb);
        if (s) {
            std::cout << "SpeedFeedback(motor1=" << s->motor1 << ", motor2=" << s->motor2 << ")\n";
        }
    }
    return 0;
}
