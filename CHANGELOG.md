# CHANGELOG

All changes are listed in the order they were applied. Each entry references the affected file, the nature of the change, and the reason.

---

## [1.0.0] — 2026-07-04

### Fixed

#### `Ammeters/client.py`
- **Changed return type from `None` to `Optional[float]`.**
  The function `request_current_from_ammeter` previously printed the received value to stdout and returned nothing. This made it impossible for any calling code to use the measurement programmatically. The function now parses the response as `float` and returns it. The print statement is retained for visibility.
- **Added `timeout: float = 3.0` parameter and `s.settimeout(timeout)` call.**
  Without a socket timeout, any server that accepted a connection but delayed or withheld its response would cause the client to block indefinitely. A 3-second default is sufficient for local TCP communication and is safely below the 4–6 second delay used by the `random_delay` fault injection scenario.

#### `Ammeters/base_ammeter.py`
- **Added `s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)` before `bind()`.**
  Without this option, if the process is killed and restarted before the OS releases the port (TIME_WAIT state), the server raises `OSError: [Errno 48] Address already in use`. This is a common pain point during iterative test development.

#### `main.py`
- **Fixed the three client command byte strings.**
  The original commented-out code sent:
  ```
  b'MEASURE_GREENLEE'
  b'MEASURE_ENTES'
  b'MEASURE_CIRCUTOR'
  ```
  The servers use strict byte equality (`if data == self.get_current_command`) against:
  ```
  b'MEASURE_GREENLEE -get_measurement'
  b'MEASURE_ENTES -get_data'
  b'MEASURE_CIRCUTOR -get_measurement -current'
  ```
  Any mismatch results in the server silently closing the connection with no response, causing the client to hang on `recv()`. This was the primary defect preventing the system from functioning at all.
- **Uncommented the client request block.** The block was commented out with the note "it shouldn't work" — confirming this was an intentional defect for the candidate to find and fix.
- **Reduced startup sleep from 5s to 2s.** Local TCP servers bind and listen in under 100ms; 2 seconds provides ample headroom.

#### `src/utils/logger.py`
- **Added `FileHandler`, `StreamHandler`, `Formatter`, and `setLevel(DEBUG)` to `_setup_logger()`.**
  The original implementation called `logging.getLogger(...)` and returned it immediately, with no handlers, no formatter, and no level set. In Python's logging system, a logger with no handlers silently drops all messages — the `info()`, `error()`, `debug()`, and `warning()` wrapper methods on `TestLogger` produced no output whatsoever.
  The fix attaches:
  - A `FileHandler` writing to `results/logs/<timestamp>_<name>.log` at level DEBUG
  - A `StreamHandler` writing to stdout at level INFO
  - A shared `Formatter` with pattern: `%(asctime)s [%(levelname)-8s] %(name)s: %(message)s`
- **Added duplicate-handler guard.** If a logger with the same name is instantiated more than once in a process, Python's logging module reuses the existing Logger object. Without the guard `if logger.handlers: return logger`, each instantiation would add another set of handlers and duplicate every log line.

#### `config/config.yaml`
- **Populated `testing.sampling` values** (were all `null`):
  - `measurements_count: 10`
  - `sampling_frequency_hz: 1.0`
  - `total_duration_seconds: null` (preserved — enables duration mode when set)
- **Uncommented the `ammeters` section** with correct ports matching `main.py` (5001/5002/5003).
- **Added `valid_range` per ammeter** derived from each device's physical measurement bounds:
  - `greenlee: [0.005, 105.0]` — I = V/R, V∈[1,10]V, R∈[0.1,100]Ω
  - `entes: [4.0, 210.0]` — I = B×K, B∈[0.01,0.1]T, K∈[500,2000]
  - `circutor: [0.0005, 0.15]` — I = Σ(V×Δt), 10 samples
- **Added `analysis`, `result_management`, and `error_simulation` sections** (see Added section below).

#### `examples/run_tests.py`
- **Added `sys.path.insert(0, project_root)` at the top of the file.**
  When a script inside a subdirectory is executed directly (`python3 examples/run_tests.py`), Python adds the script's directory to `sys.path`, not the project root. This caused `ModuleNotFoundError: No module named 'src'`. The fix computes the project root relative to `__file__` and inserts it at the front of `sys.path`.
- **Fixed `framework.run_test()` called with no arguments.**
  The method signature is `run_test(self, ammeter_type: str)` — `ammeter_type` is a required positional argument. The original call omitted it entirely, which would raise `TypeError` at runtime.
- **Replaced manual per-type loop with `framework.run_all()`** and added a formatted final results table.

---

### Added

#### `src/testing/test_framework.py` — complete implementation
The class `AmmeterTestFramework` existed as a skeleton with one unimplemented method (`run_test` returning `pass`). The following was implemented:

- **`_start_emulators()`** — Iterates over all ammeters in config, instantiates the appropriate class, and starts each in a `daemon=True` thread. Guarded by `_emulators_started` flag to prevent double-starting when called from both `run_test()` and `run_all()`. Sleeps 2 seconds for server readiness.

- **`_safe_request(port, command, valid_range)`** — Single entry point for all TCP calls. Catches and labels five exception classes:
  - `socket.timeout` → `"timeout"`
  - `ConnectionRefusedError` → `"connection_refused"`
  - `ConnectionResetError` → `"connection_reset"`
  - `ValueError` → `"malformed_response"` (float parse failure)
  - `OSError` → `"os_error"`
  - If `valid_range` is provided and the value falls outside `[lo, hi]`, returns `(None, "out_of_range")` with a WARNING log entry.

- **`_collect_samples(port, command, count, duration, frequency, valid_range)`** — Supports two modes:
  - Count mode: collects exactly `count` samples
  - Duration mode: collects as many samples as possible within `duration` seconds
  - Sleeps `1/frequency` seconds between samples. Does not sleep after the last sample.
  - Returns `(samples: List[float], errors: List[str])` tuple.

- **`_analyze(samples)`** — Computes: count, mean, median, std (ddof=1 — sample standard deviation), min, max, coefficient of variation (CV%). Uses numpy throughout. `ddof=1` is used because the samples represent a statistical sample of a device's output, not the full population.

- **`_save_result(ammeter_type, samples, stats, errors)`** — Generates a UUID run ID and writes a JSON file to `results/data/` containing: run_id, ISO timestamp, ammeter_type, config snapshot, raw samples, statistics, and error statistics. Gated by `result_management.save_json` config flag.

- **`_build_error_stats(samples, errors)`** — Static method. Aggregates error list into a summary dict: total requests, successful, failed, actual error rate, and per-type counts. Returns `None` if no errors occurred (keeps result JSON clean).

- **`_visualize(all_results)`** — Produces a three-panel matplotlib figure: time-series line chart, histogram, and box plot. Saves to `results/plots/`. Gracefully degrades with a WARNING if matplotlib is not installed. Gated by `analysis.visualization.enabled` config flag.

- **`_print_summary(results)`** — Prints an aligned summary table via the logger after all ammeters are tested. Includes error rate per device when error simulation is active.

- **`run_test(ammeter_type)`** — Orchestrates one ammeter: reads config, calls `_start_emulators()` (idempotent), calls `_collect_samples()`, calls `_analyze()`, calls `_save_result()`, logs results, returns the result dict.

- **`run_all()`** — Iterates over all configured ammeter types, calls `run_test()` for each, calls `_visualize()` if enabled, returns the combined results dict.

#### `Ammeters/Error_Simulation_Ammeter.py` — new file
`ErrorSimulationAmmeter` is a wrapper class that takes any `AmmeterEmulatorBase` instance and replaces its normal server behaviour with fault-injecting behaviour on a configurable percentage of requests. It exposes the same `start_server()` interface as a real ammeter, making it a transparent drop-in replacement in the threading context.

Four fault scenarios are implemented:
- `no_response` — accepts the connection, receives the command, then closes without sending. Simulates hardware crash or firmware hang. On the client, `recv()` returns `b''` (empty bytes from closed connection), which is caught as `"no_data"`.
- `malformed_response` — sends `b'ERROR: SENSOR_FAULT_0x7F'`. Simulates a corrupted sensor register or ADC fault. On the client, `float(...)` raises `ValueError`, caught as `"malformed_response"`.
- `extreme_value` — calls the real `measure_current()` and multiplies the result by 1000 before sending. Simulates ADC overflow or gain calibration failure. The value parses as a valid float and reaches the framework, where it is rejected by `valid_range` validation and labelled `"out_of_range"`.
- `random_delay` — sleeps 4–6 seconds before responding. The client's 3-second socket timeout fires first, raising `socket.timeout`, caught as `"timeout"`. After the delay, the server attempts to send the real measurement; if the client has already closed its socket, `BrokenPipeError` is caught silently.

Configuration via `config.yaml`:
```yaml
error_simulation:
  enabled: true
  error_rate: 0.3       # 30% of requests receive a fault
  scenarios:
    - no_response
    - malformed_response
    - extreme_value
    - random_delay
```

#### `config/config.yaml` — new sections
- `analysis.visualization.enabled: true` — gates the matplotlib output
- `result_management.output_dir / save_json` — controls JSON archiving
- `error_simulation` — full fault injection configuration (see above)

---

### Changed (Refactored)

#### `Ammeters/client.py`
- Function signature: `def request_current_from_ammeter(port, command)` → `def request_current_from_ammeter(port, command, timeout=3.0) -> Optional[float]`
- Body: returns parsed float instead of printing and returning None

#### `src/testing/test_framework.py`
- Import changed from relative (`from ..utils.config import load_config`) to absolute (`from src.utils.config import load_config`) for consistency with the rest of the codebase and to support direct script execution from the project root
- `run_test()` return type annotation added: `-> Dict`

---

### Libraries Installed

All libraries were already listed in `requirements.txt`. No new dependencies were introduced.

```
numpy>=1.21.0
scipy>=1.7.0
matplotlib>=3.4.0
seaborn>=0.11.0
pyyaml>=6.0
pandas>=1.3.0
```

Install with:
```bash
pip install -r requirements.txt
```

---

### Output Artefacts Produced

| Path | Contents |
|---|---|
| `results/logs/<timestamp>_ammeter_framework.log` | Full structured log of every test run |
| `results/data/<timestamp>_<uuid8>_<ammeter>.json` | Per-ammeter result: run_id, timestamp, config snapshot, raw samples, statistics, error stats |
| `results/plots/<timestamp>_comparison.png` | Three-panel figure: time series, histogram, box plot |
