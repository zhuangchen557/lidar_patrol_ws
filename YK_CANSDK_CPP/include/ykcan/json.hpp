#pragma once
/* Minimal self-contained JSON parser/serializer (subset used by the SDK).
 *
 * Matches the SDK philosophy of "no third-party runtime dependencies".
 * Supports: null, true/false, numbers (int/float), strings (with escapes),
 * objects (preserving insertion order) and arrays.
 */

#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace yk_can {
namespace json {

class Value {
public:
    enum class Type { Null, Bool, Number, String, Array, Object };

    Value() : type_(Type::Null) {}
    static Value null() { return Value(); }
    static Value boolean(bool b) { Value v; v.type_ = Type::Bool; v.bool_ = b; return v; }
    static Value number(double n) { Value v; v.type_ = Type::Number; v.number_ = n; return v; }
    static Value string(std::string s) { Value v; v.type_ = Type::String; v.string_ = std::move(s); return v; }
    static Value array() { Value v; v.type_ = Type::Array; return v; }
    static Value object() { Value v; v.type_ = Type::Object; return v; }

    Type type() const { return type_; }
    bool is_null() const { return type_ == Type::Null; }
    bool is_bool() const { return type_ == Type::Bool; }
    bool is_number() const { return type_ == Type::Number; }
    bool is_string() const { return type_ == Type::String; }
    bool is_array() const { return type_ == Type::Array; }
    bool is_object() const { return type_ == Type::Object; }

    bool as_bool() const {
        if (type_ != Type::Bool) throw std::runtime_error("expected boolean in JSON");
        return bool_;
    }

    double as_number() const {
        if (type_ != Type::Number) throw std::runtime_error("expected number in JSON");
        return number_;
    }

    std::int64_t as_int() const { return std::llround(as_number()); }
    int as_int32() const { return static_cast<int>(as_int()); }

    const std::string& as_string() const {
        if (type_ != Type::String) throw std::runtime_error("expected string in JSON");
        return string_;
    }

    const std::vector<std::pair<std::string, Value>>& members() const {
        if (type_ != Type::Object) throw std::runtime_error("expected object in JSON");
        return object_;
    }

    const Value* find(const std::string& key) const {
        if (type_ != Type::Object) return nullptr;
        for (const auto& kv : object_) {
            if (kv.first == key) return &kv.second;
        }
        return nullptr;
    }

    bool has(const std::string& key) const { return find(key) != nullptr; }

    void insert(const std::string& key, Value value) {
        if (type_ != Type::Object) throw std::runtime_error("expected object in JSON");
        for (auto& kv : object_) {
            if (kv.first == key) { kv.second = std::move(value); return; }
        }
        object_.emplace_back(key, std::move(value));
    }

    size_t size() const {
        if (type_ == Type::Array) return array_.size();
        if (type_ == Type::Object) return object_.size();
        throw std::runtime_error("expected array or object in JSON");
    }

    const Value* at(size_t index) const {
        if (type_ != Type::Array) throw std::runtime_error("expected array in JSON");
        if (index >= array_.size()) throw std::runtime_error("array index out of range");
        return &array_[index];
    }

    void push(Value value) {
        if (type_ != Type::Array) throw std::runtime_error("expected array in JSON");
        array_.push_back(std::move(value));
    }

    /* Tolerant accessors used for config fields. */
    bool bool_or(bool fallback) const { return is_null() ? fallback : as_bool(); }
    double number_or(double fallback) const { return is_number() ? number_ : fallback; }
    int int_or(int fallback) const { return is_number() ? as_int32() : fallback; }
    std::string string_or(const std::string& fallback) const {
        return is_string() ? string_ : fallback;
    }

    std::string dump(bool pretty = true, int indent_width = 2) const;

    static Value parse(const std::string& text) { return Parser(text).parse(); }

private:
    Type type_ = Type::Null;
    bool bool_ = false;
    double number_ = 0.0;
    std::string string_;
    std::vector<std::pair<std::string, Value>> object_;
    std::vector<Value> array_;

    void dump_into(std::string& out, int indent, int indent_width) const {
        if (indent < 0) {  // compact
            switch (type_) {
                case Type::Null: out += "null"; break;
                case Type::Bool: out += (bool_ ? "true" : "false"); break;
                case Type::Number: {
                    char buf[64];
                    if (number_ == static_cast<double>(std::llround(number_)) &&
                        std::fabs(number_) < 9.0e15) {
                        std::snprintf(buf, sizeof(buf), "%lld", std::llround(number_));
                    } else {
                        std::snprintf(buf, sizeof(buf), "%.17g", number_);
                    }
                    out += buf;
                    break;
                }
                case Type::String: escape_into(out, string_); break;
                case Type::Array: {
                    out += '[';
                    for (size_t i = 0; i < array_.size(); ++i) {
                        if (i) out += ',';
                        array_[i].dump_into(out, -1, indent_width);
                    }
                    out += ']';
                    break;
                }
                case Type::Object: {
                    out += '{';
                    for (size_t i = 0; i < object_.size(); ++i) {
                        if (i) out += ',';
                        escape_into(out, object_[i].first);
                        out += ':';
                        object_[i].second.dump_into(out, -1, indent_width);
                    }
                    out += '}';
                    break;
                }
            }
            return;
        }

        if (type_ == Type::Object) {
            if (object_.empty()) { out += "{}"; return; }
            out += "{\n";
            for (size_t i = 0; i < object_.size(); ++i) {
                out += std::string(static_cast<size_t>((indent + 1) * indent_width), ' ');
                escape_into(out, object_[i].first);
                out += ": ";
                object_[i].second.dump_into(out, indent + 1, indent_width);
                if (i + 1 < object_.size()) out += ',';
                out += '\n';
            }
            out += std::string(static_cast<size_t>(indent * indent_width), ' ');
            out += '}';
            return;
        }
        if (type_ == Type::Array) {
            if (array_.empty()) { out += "[]"; return; }
            out += "[\n";
            for (size_t i = 0; i < array_.size(); ++i) {
                out += std::string(static_cast<size_t>((indent + 1) * indent_width), ' ');
                array_[i].dump_into(out, indent + 1, indent_width);
                if (i + 1 < array_.size()) out += ',';
                out += '\n';
            }
            out += std::string(static_cast<size_t>(indent * indent_width), ' ');
            out += ']';
            return;
        }
        {
            std::string compact;
            dump_into(compact, -1, indent_width);
            out += compact;
        }
    }

    class Parser {
    public:
        explicit Parser(const std::string& text) : text_(text) {}

        Value parse() {
            Value v = parse_value();
            skip_ws();
            if (pos_ != text_.size()) fail("unexpected trailing characters");
            return v;
        }

    private:
        const std::string& text_;
        size_t pos_ = 0;

        [[noreturn]] void fail(const std::string& msg) const {
            throw std::runtime_error("json parse error at offset " + std::to_string(pos_) + ": " + msg);
        }
        void skip_ws() {
            while (pos_ < text_.size() && std::isspace(static_cast<unsigned char>(text_[pos_]))) ++pos_;
        }
        char peek() const { return pos_ < text_.size() ? text_[pos_] : '\0'; }
        char next() {
            if (pos_ >= text_.size()) fail("unexpected end of input");
            return text_[pos_++];
        }
        void expect(char c) {
            if (next() != c) fail(std::string("expected '") + c + "'");
        }

        Value parse_value() {
            skip_ws();
            char c = next();
            if (c == 'n') { expect('u'); expect('l'); expect('l'); return Value::null(); }
            if (c == 't') { expect('r'); expect('u'); expect('e'); return Value::boolean(true); }
            if (c == 'f') { expect('a'); expect('l'); expect('s'); expect('e'); return Value::boolean(false); }
            if (c == '"') { --pos_; return parse_string(); }
            if (c == '[') return parse_array();
            if (c == '{') return parse_object();
            if (c == '-' || (c >= '0' && c <= '9')) { --pos_; return parse_number(); }
            fail("unexpected character");
        }

        Value parse_string() {
            expect('"');
            std::string out;
            for (;;) {
                char c = next();
                if (c == '"') break;
                if (c == '\\') {
                    char e = next();
                    switch (e) {
                        case '"': out += '"'; break;
                        case '\\': out += '\\'; break;
                        case '/': out += '/'; break;
                        case 'b': out += '\b'; break;
                        case 'f': out += '\f'; break;
                        case 'n': out += '\n'; break;
                        case 'r': out += '\r'; break;
                        case 't': out += '\t'; break;
                        case 'u': append_utf8(out, parse_hex()); break;
                        default: fail("invalid escape sequence");
                    }
                } else {
                    if (static_cast<unsigned char>(c) < 0x20) fail("unescaped control character");
                    out += c;
                }
            }
            return Value::string(std::move(out));
        }

        unsigned parse_hex() {
            unsigned v = 0;
            for (int i = 0; i < 4; ++i) {
                char c = next();
                v <<= 4;
                if (c >= '0' && c <= '9') v |= static_cast<unsigned>(c - '0');
                else if (c >= 'a' && c <= 'f') v |= static_cast<unsigned>(c - 'a' + 10);
                else if (c >= 'A' && c <= 'F') v |= static_cast<unsigned>(c - 'A' + 10);
                else fail("invalid unicode escape");
            }
            return v;
        }

        static void append_utf8(std::string& out, unsigned cp) {
            if (cp < 0x80) {
                out += static_cast<char>(cp);
            } else if (cp < 0x800) {
                out += static_cast<char>(0xC0 | (cp >> 6));
                out += static_cast<char>(0x80 | (cp & 0x3F));
            } else if (cp < 0x10000) {
                out += static_cast<char>(0xE0 | (cp >> 12));
                out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
                out += static_cast<char>(0x80 | (cp & 0x3F));
            } else {
                out += static_cast<char>(0xF0 | (cp >> 18));
                out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
                out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
                out += static_cast<char>(0x80 | (cp & 0x3F));
            }
        }

        Value parse_number() {
            size_t start = pos_;
            if (peek() == '-') ++pos_;
            if (peek() == '0') ++pos_;
            else if (peek() >= '1' && peek() <= '9') {
                while (peek() >= '0' && peek() <= '9') ++pos_;
            } else {
                fail("invalid number");
            }
            if (peek() == '.') {
                ++pos_;
                if (!(peek() >= '0' && peek() <= '9')) fail("missing fractional digits");
                while (peek() >= '0' && peek() <= '9') ++pos_;
            }
            if (peek() == 'e' || peek() == 'E') {
                ++pos_;
                if (peek() == '+' || peek() == '-') ++pos_;
                if (!(peek() >= '0' && peek() <= '9')) fail("missing exponent digits");
                while (peek() >= '0' && peek() <= '9') ++pos_;
            }
            std::string token = text_.substr(start, pos_ - start);
            char* end = nullptr;
            double value = std::strtod(token.c_str(), &end);
            if (end == nullptr || *end != '\0') fail("invalid number");
            return Value::number(value);
        }

        Value parse_array() {
            Value arr = Value::array();
            skip_ws();
            if (peek() == ']') { ++pos_; return arr; }
            for (;;) {
                arr.push(parse_value());
                skip_ws();
                if (peek() == ',') { ++pos_; continue; }
                if (peek() == ']') { ++pos_; break; }
                fail("expected ',' or ']'");
            }
            return arr;
        }

        Value parse_object() {
            Value obj = Value::object();
            skip_ws();
            if (peek() == '}') { ++pos_; return obj; }
            for (;;) {
                skip_ws();
                Value keyv = parse_value();
                if (keyv.type() != Type::String) fail("object key must be a string");
                skip_ws();
                expect(':');
                Value value = parse_value();
                obj.insert(keyv.as_string(), std::move(value));
                skip_ws();
                if (peek() == ',') { ++pos_; continue; }
                if (peek() == '}') { ++pos_; break; }
                fail("expected ',' or '}'");
            }
            return obj;
        }
    };

    static void escape_into(std::string& out, const std::string& s) {
        out += '"';
        for (unsigned char c : s) {
            switch (c) {
                case '"': out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                case '\b': out += "\\b"; break;
                case '\f': out += "\\f"; break;
                default:
                    if (c < 0x20) {
                        char buf[8];
                        std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                        out += buf;
                    } else {
                        out += static_cast<char>(c);
                    }
            }
        }
        out += '"';
    }
};

inline std::string Value::dump(bool pretty, int indent_width) const {
    std::string out;
    dump_into(out, pretty ? 0 : -1, indent_width);
    return out;
}

}  // namespace json
}  // namespace yk_can