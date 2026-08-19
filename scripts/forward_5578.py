"""TCP 转发器：Windows 127.0.0.1:5578 <-> CAN115 192.168.0.7:5578
供 WSL 内的底盘 SDK 通过 localhost 访问 CAN115"""
import socket
import threading
import sys

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 5578
TARGET_HOST = "192.168.0.7"
TARGET_PORT = 5578


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
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass


def handle(client):
    try:
        target = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=5)
        print(f"[+] relay: client -> {TARGET_HOST}:{TARGET_PORT}", flush=True)
        threading.Thread(target=pipe, args=(client, target, "c2t"), daemon=True).start()
        threading.Thread(target=pipe, args=(target, client, "t2c"), daemon=True).start()
    except Exception as e:
        print(f"[-] connect target failed: {e}", flush=True)
        client.close()


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