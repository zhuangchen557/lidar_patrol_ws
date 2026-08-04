#pragma once
/* Minimal cross-platform TCP socket wrapper (Winsock2 on Windows).
 *
 * Used by GatewayClient; mirrors the Python socket semantics used by the
 * reference SDK: create_connection with timeout + settimeout, sendall and
 * recv with timeout. Bytes on the wire are byte-for-byte identical.
 */

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
using NativeSocket = SOCKET;
inline constexpr NativeSocket kInvalidNativeSocket = INVALID_SOCKET;
#else
#include <arpa/inet.h>
#include <cerrno>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
using NativeSocket = int;
inline constexpr NativeSocket kInvalidNativeSocket = -1;
#endif

namespace yk_can {

namespace net_detail {

inline void ensure_wsa_initialized() {
#ifdef _WIN32
    static bool done = false;
    if (!done) {
        WSADATA wsa;
        ::WSAStartup(MAKEWORD(2, 2), &wsa);
        done = true;
    }
#else
    (void)0;
#endif
}

inline int last_socket_error() {
#ifdef _WIN32
    return WSAGetLastError();
#else
    return errno;
#endif
}

inline void close_fd(NativeSocket fd) {
#ifdef _WIN32
    ::closesocket(fd);
#else
    ::close(fd);
#endif
}

inline void set_nonblocking(NativeSocket fd, bool on) {
#ifdef _WIN32
    u_long flag = on ? 1UL : 0UL;
    ::ioctlsocket(fd, FIONBIO, &flag);
#else
    int flags = ::fcntl(fd, F_GETFL, 0);
    if (flags < 0) return;
    if (on) flags |= O_NONBLOCK;
    else flags &= ~O_NONBLOCK;
    ::fcntl(fd, F_SETFL, flags);
#endif
}

inline int would_block_error() {
#ifdef _WIN32
    return WSAEWOULDBLOCK;
#else
    return EINPROGRESS;
#endif
}

/* Wait up to timeout_s for fd to become writable. Returns true if so. */
inline bool wait_writable(NativeSocket fd, double timeout_s) {
    struct timeval tv;
    tv.tv_sec = static_cast<long>(timeout_s);
    tv.tv_usec = static_cast<long>((timeout_s - tv.tv_sec) * 1.0e6);
    fd_set wfds;
    FD_ZERO(&wfds);
    FD_SET(fd, &wfds);
    int r = ::select(static_cast<int>(fd) + 1, nullptr, &wfds, nullptr, &tv);
    return r > 0;
}

}  // namespace net_detail

class TcpSocket {
public:
    TcpSocket() = default;
    explicit TcpSocket(NativeSocket handle) : handle_(handle) {}
    ~TcpSocket() { close(); }

    TcpSocket(const TcpSocket&) = delete;
    TcpSocket& operator=(const TcpSocket&) = delete;

    TcpSocket(TcpSocket&& other) noexcept : handle_(other.handle_) { other.handle_ = kInvalidNativeSocket; }
    TcpSocket& operator=(TcpSocket&& other) noexcept {
        if (this != &other) {
            close();
            handle_ = other.handle_;
            other.handle_ = kInvalidNativeSocket;
        }
        return *this;
    }

    bool valid() const { return handle_ != kInvalidNativeSocket; }
    explicit operator bool() const { return valid(); }

    void close() noexcept {
        if (!valid()) return;
        net_detail::close_fd(handle_);
        handle_ = kInvalidNativeSocket;
    }

    /* Match Python settimeout(): applied to BOTH receive and send operations,
     * so a stuck peer cannot hang the control thread forever. */
    void set_receive_timeout(double seconds) {
        if (!valid()) return;
#ifdef _WIN32
        DWORD ms = static_cast<DWORD>(seconds * 1000.0);
        ::setsockopt(handle_, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&ms), sizeof(ms));
        ::setsockopt(handle_, SOL_SOCKET, SO_SNDTIMEO, reinterpret_cast<const char*>(&ms), sizeof(ms));
#else
        struct timeval tv;
        tv.tv_sec = static_cast<long>(seconds);
        tv.tv_usec = static_cast<long>((seconds - tv.tv_sec) * 1.0e6);
        ::setsockopt(handle_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
        ::setsockopt(handle_, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#endif
    }

    void send_all(const uint8_t* data, size_t length) {
        net_detail::ensure_wsa_initialized();
        size_t sent = 0;
        while (sent < length) {
            int chunk = static_cast<int>(length - sent);
            int r = ::send(handle_, reinterpret_cast<const char*>(data + sent), chunk, 0);
            if (r < 0) {
                throw std::runtime_error("failed to send to CAN115 (errno=" +
                                         std::to_string(net_detail::last_socket_error()) + ")");
            }
            sent += static_cast<size_t>(r);
        }
    }

    void send_all(const uint8_t* begin, const uint8_t* end) {
        send_all(begin, static_cast<size_t>(end - begin));
    }

    /* Returns:
     *   >0  bytes read
     *    0  orderly close (peer FIN)
     *   -1  receive timeout (set_receive_timeout expired with no data)
     * throws std::runtime_error on a hard socket error.
     */
    ptrdiff_t recv(uint8_t* buf, size_t capacity) {
        if (capacity == 0) return 0;
        int want = static_cast<int>(capacity);
        int r = ::recv(handle_, reinterpret_cast<char*>(buf), want, 0);
        if (r < 0) {
            int err = net_detail::last_socket_error();
#ifdef _WIN32
            if (err == WSAETIMEDOUT) return -1;
#else
            if (err == EAGAIN || err == EWOULDBLOCK || err == EINTR) return -1;
#endif
            throw std::runtime_error("socket recv failed (errno error " + std::to_string(err) + ")");
        }
        return r;
    }

    void shutdown_both() noexcept {
        if (!valid()) return;
#ifdef _WIN32
        ::shutdown(handle_, SD_BOTH);
#else
        ::shutdown(handle_, SHUT_RDWR);
#endif
    }

    /* Non-blocking connect honoring timeout_ms; Python socket.create_connection
     * semantics. Throws std::runtime_error on resolution or connect failure. */
    static TcpSocket connect(const std::string& host, uint16_t port, double timeout_s) {
        net_detail::ensure_wsa_initialized();
        std::string port_str = std::to_string(port);

        addrinfo hints;
        std::memset(&hints, 0, sizeof(hints));
        hints.ai_family = AF_INET;         /* CAN115 is IPv4 on the LAN. */
        hints.ai_socktype = SOCK_STREAM;
        hints.ai_protocol = IPPROTO_TCP;

        addrinfo* result = nullptr;
        int rc = ::getaddrinfo(host.c_str(), port_str.c_str(), &hints, &result);
        if (rc != 0) {
            throw std::runtime_error("cannot resolve host '" + host + "': getaddrinfo returned " +
                                     std::to_string(rc));
        }

        NativeSocket connected_fd = kInvalidNativeSocket;
        for (addrinfo* ai = result; ai != nullptr; ai = ai->ai_next) {
            NativeSocket fd = ::socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
            if (fd == kInvalidNativeSocket) continue;

            net_detail::set_nonblocking(fd, true);
            int r = ::connect(fd, ai->ai_addr, static_cast<int>(ai->ai_addrlen));
            if (r != 0) {
                int err = net_detail::last_socket_error();
                if (err == net_detail::would_block_error() &&
                    net_detail::wait_writable(fd, timeout_s)) {
                    int soerr = 0;
#ifdef _WIN32
                    int soerr_len = static_cast<int>(sizeof(soerr));
                    ::getsockopt(fd, SOL_SOCKET, SO_ERROR, reinterpret_cast<char*>(&soerr), &soerr_len);
#else
                    socklen_t soerr_len = sizeof(soerr);
                    ::getsockopt(fd, SOL_SOCKET, SO_ERROR, &soerr, &soerr_len);
#endif
                    if (soerr == 0) {
                        connected_fd = fd;
                        break;
                    }
                }
                net_detail::close_fd(fd);
                continue;
            }
            connected_fd = fd;
            break;
        }
        ::freeaddrinfo(result);

        if (connected_fd == kInvalidNativeSocket) {
            throw std::runtime_error("cannot connect to " + host + ":" + port_str);
        }
        net_detail::set_nonblocking(connected_fd, false);
        return TcpSocket(connected_fd);
    }

private:
    NativeSocket handle_ = kInvalidNativeSocket;
};

}  // namespace yk_can