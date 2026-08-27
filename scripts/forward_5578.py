"""TCP 转发器：127.0.0.1:5578 <-> CAN115 192.168.0.7:5578
供 WSL 内的底盘 SDK 通过 localhost 访问 CAN115
注意：CAN115 只允许一个 TCP 客户端，因此本转发器同一时刻只保留一个活动连接
"""
import socket
import threading

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 5578
TARGET_HOST = "192.168.0.7"
TARGET_PORT = 5578

_lock = threading.Lock()
_active = {"client": None, "target": None}


def _swap(conns):
    """锁内交换连接引用，返回旧连接（调用方在锁外关闭）"""
    with _lock:
        old = (_active["client"], _active["target"])
        _active["client"] = conns[0]
        _active["target"] = conns[1]
    return old


def _close(socks):
    for s in socks:
        if s:
            try:
                s.close()
            except Exception:
                pass


def pipe(src, dst, name):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        _close((src, dst))
        _close(_swap((None, None)))


def handle(client):
    try:
        target = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=5)
    except Exception as e:
        print(f"[-] connect target failed: {e}", flush=True)
        client.close()
        return
    old = _swap((client, target))
    _close(old)
    print(f"[+] relay: client -> {TARGET_HOST}:{TARGET_PORT}", flush=True)
    threading.Thread(target=pipe, args=(client, target, "c2t"), daemon=True).start()
    threading.Thread(target=pipe, args=(target, client, "t2c"), daemon=True).start()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(5)
    print(f"[*] relay {LISTEN_HOST}:{LISTEN_PORT} -> {TARGET_HOST}:{TARGET_PORT}", flush=True)
    while True:
        client, _ = srv.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
