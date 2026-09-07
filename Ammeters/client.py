from socket import socket, AF_INET, SOCK_STREAM
from typing import Optional


def request_current_from_ammeter(
    port: int, command: bytes, timeout: float = 3.0
) -> Optional[float]:
    with socket(AF_INET, SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(('localhost', port))
        s.sendall(command)
        data = s.recv(1024)
        if data:
            value = float(data.decode('utf-8'))
            print(f"Received current measurement from port {port}: {value} A")
            return value
        print("No data received.")
        return None
