import random
import socket
import time
from typing import List

from Ammeters.base_ammeter import AmmeterEmulatorBase


class ErrorSimulationAmmeter:
    """
    Wraps any AmmeterEmulatorBase and randomly injects faults on a configurable
    percentage of requests. Mirrors the start_server() interface so it can be
    dropped in wherever a real emulator is used.

    Supported scenarios:
        no_response       - accepts connection, receives command, closes without replying
                           (simulates hardware crash / bus hang)
        malformed_response - sends a non-numeric payload that cannot be parsed as float
                           (simulates sensor fault / corrupted ADC register)
        extreme_value     - sends a value 1000x the real measurement
                           (simulates ADC overflow / gain calibration failure)
        random_delay      - delays response past the client socket timeout
                           (simulates bus contention / frozen firmware)
    """

    VALID_SCENARIOS = {"no_response", "malformed_response", "extreme_value", "random_delay"}

    def __init__(
        self,
        ammeter: AmmeterEmulatorBase,
        error_rate: float,
        scenarios: List[str],
        response_delay_range: tuple = (4.0, 6.0),
    ):
        unknown = set(scenarios) - self.VALID_SCENARIOS
        if unknown:
            raise ValueError(f"Unknown error scenarios: {unknown}. Valid: {self.VALID_SCENARIOS}")

        self._ammeter = ammeter
        self._error_rate = max(0.0, min(1.0, error_rate))
        self._scenarios = scenarios
        self._response_delay_range = response_delay_range
        self.port = ammeter.port

        self._request_count = 0
        self._error_count = 0

    def start_server(self) -> None:
        name = self._ammeter.__class__.__name__
        print(
            f"[ERROR SIM] {name} running on port {self.port} "
            f"| error_rate={self._error_rate:.0%} "
            f"| scenarios={self._scenarios}"
        )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("localhost", self.port))
            s.listen()
            while True:
                conn, addr = s.accept()
                with conn:
                    data = conn.recv(1024)
                    if data != self._ammeter.get_current_command:
                        continue  # wrong command — ignore silently (same as base class)

                    self._request_count += 1

                    if random.random() < self._error_rate:
                        self._error_count += 1
                        scenario = random.choice(self._scenarios)
                        self._inject_error(conn, scenario)
                    else:
                        current = self._ammeter.measure_current()
                        conn.sendall(str(current).encode("utf-8"))

    def _inject_error(self, conn: socket.socket, scenario: str) -> None:
        name = self._ammeter.__class__.__name__
        print(f"[ERROR SIM] {name} port={self.port} → injecting '{scenario}'")

        if scenario == "no_response":
            pass  # 'with conn' context manager closes connection without sending

        elif scenario == "malformed_response":
            conn.sendall(b"ERROR: SENSOR_FAULT_0x7F")

        elif scenario == "extreme_value":
            real = self._ammeter.measure_current()
            conn.sendall(str(real * 1000.0).encode("utf-8"))

        elif scenario == "random_delay":
            delay = random.uniform(*self._response_delay_range)
            print(f"[ERROR SIM] {name} port={self.port} → sleeping {delay:.1f}s (client will time out)")
            time.sleep(delay)
            try:
                current = self._ammeter.measure_current()
                conn.sendall(str(current).encode("utf-8"))
            except (BrokenPipeError, OSError):
                pass  # client already timed out and closed its end
