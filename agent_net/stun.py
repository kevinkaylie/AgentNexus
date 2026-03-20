"""
STUN 模块 - 获取公网IP映射，支持NAT穿透
"""
import asyncio
import socket
import struct
import time

STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
]

MAGIC_COOKIE = 0x2112A442
BINDING_REQUEST = 0x0001
BINDING_RESPONSE = 0x0101
XOR_MAPPED_ADDRESS = 0x0020
MAPPED_ADDRESS = 0x0001


def _build_binding_request() -> tuple[bytes, bytes]:
    transaction_id = bytes([i % 256 for i in range(12)])
    msg = struct.pack(">HHI", BINDING_REQUEST, 0, MAGIC_COOKIE) + transaction_id
    return msg, transaction_id


def _parse_response(data: bytes) -> tuple[str, int] | None:
    if len(data) < 20:
        return None
    msg_type, msg_len, magic = struct.unpack(">HHI", data[:8])
    if msg_type != BINDING_RESPONSE:
        return None

    offset = 20
    while offset < len(data):
        if offset + 4 > len(data):
            break
        attr_type, attr_len = struct.unpack(">HH", data[offset:offset+4])
        offset += 4
        attr_val = data[offset:offset+attr_len]
        offset += attr_len + (4 - attr_len % 4) % 4  # 4-byte align

        if attr_type == XOR_MAPPED_ADDRESS and len(attr_val) >= 8:
            family = attr_val[1]
            if family == 0x01:  # IPv4
                port = struct.unpack(">H", attr_val[2:4])[0] ^ (MAGIC_COOKIE >> 16)
                ip_int = struct.unpack(">I", attr_val[4:8])[0] ^ MAGIC_COOKIE
                ip = socket.inet_ntoa(struct.pack(">I", ip_int))
                return ip, port
        elif attr_type == MAPPED_ADDRESS and len(attr_val) >= 8:
            family = attr_val[1]
            if family == 0x01:
                port = struct.unpack(">H", attr_val[2:4])[0]
                ip = socket.inet_ntoa(attr_val[4:8])
                return ip, port
    return None


async def get_public_endpoint(timeout: float = 3.0) -> dict | None:
    """通过STUN获取公网IP和端口"""
    loop = asyncio.get_event_loop()

    for server_host, server_port in STUN_SERVERS:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            request, _ = _build_binding_request()

            server_addr = await loop.run_in_executor(
                None, lambda: (socket.gethostbyname(server_host), server_port)
            )
            await loop.sock_sendto(sock, request, server_addr)

            data = await asyncio.wait_for(
                loop.sock_recv(sock, 1024), timeout=timeout
            )
            result = _parse_response(data)
            sock.close()

            if result:
                ip, port = result
                return {
                    "public_ip": ip,
                    "public_port": port,
                    "stun_server": f"{server_host}:{server_port}",
                    "timestamp": time.time(),
                }
        except Exception:
            continue
        finally:
            try:
                sock.close()
            except Exception:
                pass

    return None
