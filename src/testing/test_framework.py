import json
import os
import threading
import time
import uuid
from datetime import datetime
from socket import timeout as SocketTimeout
from typing import Dict, List, Optional, Tuple

import numpy as np

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.client import request_current_from_ammeter
from src.utils.config import load_config
from src.utils.logger import TestLogger

_AMMETER_CLASSES = {
    "greenlee": GreenleeAmmeter,
    "entes": EntesAmmeter,
    "circutor": CircutorAmmeter,
}

_STARTUP_WAIT_SECONDS = 2.0


class AmmeterTestFramework:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        self.logger = TestLogger("ammeter_framework")
        self._emulators_started = False

    # ------------------------------------------------------------------
    # Emulator startup
    # ------------------------------------------------------------------

    def _start_emulators(self) -> None:
        if self._emulators_started:
            return

        error_sim_cfg = self.config.get("error_simulation") or {}
        error_sim_enabled = error_sim_cfg.get("enabled", False)
        error_rate = float(error_sim_cfg.get("error_rate", 0.3))
        scenarios = error_sim_cfg.get("scenarios") or [
            "no_response", "malformed_response", "extreme_value", "random_delay"
        ]

        if error_sim_enabled:
            from Ammeters.Error_Simulation_Ammeter import ErrorSimulationAmmeter

        ammeter_configs = self.config.get("ammeters", {})
        for name, cfg in ammeter_configs.items():
            ammeter_class = _AMMETER_CLASSES.get(name)
            if ammeter_class is None:
                self.logger.warning(f"Unknown ammeter type '{name}' in config — skipping")
                continue

            port = cfg["port"]
            real_emulator = ammeter_class(port)

            if error_sim_enabled:
                emulator = ErrorSimulationAmmeter(real_emulator, error_rate, scenarios)
                self.logger.info(
                    f"Started {name} emulator [ERROR SIM on, rate={error_rate:.0%}, "
                    f"scenarios={scenarios}] on port {port}"
                )
            else:
                emulator = real_emulator
                self.logger.info(f"Started {name} emulator on port {port}")

            thread = threading.Thread(
                target=emulator.start_server,
                name=f"emulator-{name}",
                daemon=True,
            )
            thread.start()

        self.logger.info(f"Waiting {_STARTUP_WAIT_SECONDS}s for emulators to be ready...")
        time.sleep(_STARTUP_WAIT_SECONDS)
        self._emulators_started = True

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def _safe_request(
        self,
        port: int,
        command: bytes,
        valid_range: Optional[Tuple[float, float]] = None,
    ) -> Tuple[Optional[float], Optional[str]]:
        """
        Wraps request_current_from_ammeter and converts every failure mode into
        a labelled error string so the caller can collect stats without crashing.
        """
        try:
            value = request_current_from_ammeter(port, command)
            if value is None:
                return None, "no_data"
            if valid_range is not None:
                lo, hi = valid_range
                if not (lo <= value <= hi):
                    self.logger.warning(
                        f"  port {port} → OUT OF RANGE: {value:.6f}A not in [{lo}, {hi}] — rejected"
                    )
                    return None, "out_of_range"
            return value, None
        except SocketTimeout:
            self.logger.warning(f"  port {port} → TIMEOUT (server delayed past socket limit)")
            return None, "timeout"
        except ConnectionRefusedError:
            self.logger.warning(f"  port {port} → CONNECTION REFUSED (server not running?)")
            return None, "connection_refused"
        except ConnectionResetError:
            self.logger.warning(f"  port {port} → CONNECTION RESET (server closed abruptly)")
            return None, "connection_reset"
        except ValueError as exc:
            self.logger.warning(f"  port {port} → PARSE ERROR (malformed response): {exc}")
            return None, "malformed_response"
        except OSError as exc:
            self.logger.warning(f"  port {port} → OS ERROR: {exc}")
            return None, f"os_error"

    def _collect_samples(
        self,
        port: int,
        command: bytes,
        count: Optional[int],
        duration: Optional[float],
        frequency: float,
        valid_range: Optional[Tuple[float, float]] = None,
    ) -> Tuple[List[float], List[str]]:
        samples: List[float] = []
        errors: List[str] = []
        interval = 1.0 / frequency

        if duration is not None:
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                value, error = self._safe_request(port, command, valid_range)
                if value is not None:
                    samples.append(value)
                if error:
                    errors.append(error)
                time.sleep(interval)
        else:
            for i in range(count):
                value, error = self._safe_request(port, command, valid_range)
                if value is not None:
                    samples.append(value)
                if error:
                    errors.append(error)
                if i < count - 1:
                    time.sleep(interval)

        return samples, errors

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _analyze(self, samples: List[float]) -> Dict:
        arr = np.array(samples, dtype=float)
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        cv = (std / mean * 100.0) if mean != 0.0 else 0.0

        return {
            "count": len(arr),
            "mean": mean,
            "median": float(np.median(arr)),
            "std": std,
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "cv_percent": cv,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_result(
        self,
        ammeter_type: str,
        samples: List[float],
        stats: Dict,
        errors: List[str],
    ) -> str:
        rm_config = self.config.get("result_management", {}) or {}
        if not rm_config.get("save_json", True):
            return ""

        output_dir = rm_config.get("output_dir", "results/data")
        os.makedirs(output_dir, exist_ok=True)

        run_id = str(uuid.uuid4())
        timestamp = datetime.now()

        error_stats = self._build_error_stats(samples, errors)

        result = {
            "run_id": run_id,
            "timestamp": timestamp.isoformat(),
            "ammeter_type": ammeter_type,
            "config_snapshot": (self.config.get("testing", {}) or {}).get("sampling", {}),
            "error_simulation": error_stats,
            "samples": samples,
            "statistics": stats,
        }

        filename = (
            f"{output_dir}/"
            f"{timestamp.strftime('%Y%m%d_%H%M%S')}"
            f"_{run_id[:8]}"
            f"_{ammeter_type}.json"
        )
        with open(filename, "w") as f:
            json.dump(result, f, indent=2)

        self.logger.info(f"Saved results → {filename}")
        return run_id

    @staticmethod
    def _build_error_stats(samples: List[float], errors: List[str]) -> Optional[Dict]:
        if not errors:
            return None

        total = len(samples) + len(errors)
        counts: Dict[str, int] = {}
        for e in errors:
            counts[e] = counts.get(e, 0) + 1

        return {
            "total_requests": total,
            "successful": len(samples),
            "failed": len(errors),
            "actual_error_rate": round(len(errors) / total, 3),
            "by_type": counts,
        }

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    def _visualize(self, all_results: Dict[str, Dict]) -> None:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            self.logger.warning("matplotlib not installed — skipping visualization")
            return

        output_dir = "results/plots"
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        fig, axes = plt.subplots(1, 3, figsize=(18, 5))
        fig.suptitle("Ammeter Current Measurements Comparison", fontsize=14)

        ax = axes[0]
        for name, result in all_results.items():
            if "samples" in result:
                ax.plot(result["samples"], label=name, marker="o", markersize=3, linewidth=1)
        ax.set_title("Time Series")
        ax.set_xlabel("Sample #")
        ax.set_ylabel("Current (A)")
        ax.legend()
        ax.grid(True, alpha=0.3)

        ax = axes[1]
        for name, result in all_results.items():
            if "samples" in result:
                ax.hist(result["samples"], alpha=0.6, label=name, bins=10)
        ax.set_title("Distribution")
        ax.set_xlabel("Current (A)")
        ax.set_ylabel("Frequency")
        ax.legend()
        ax.grid(True, alpha=0.3)

        ax = axes[2]
        valid = {k: v for k, v in all_results.items() if "samples" in v}
        if valid:
            ax.boxplot(
                [v["samples"] for v in valid.values()],
                labels=list(valid.keys()),
                patch_artist=True,
            )
        ax.set_title("Consistency (lower spread = more reliable)")
        ax.set_ylabel("Current (A)")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plot_path = f"{output_dir}/{timestamp}_comparison.png"
        plt.savefig(plot_path, dpi=150, bbox_inches="tight")
        plt.close()
        self.logger.info(f"Saved visualization → {plot_path}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_test(self, ammeter_type: str) -> Dict:
        """Collect samples from one ammeter, analyze, save, and return the result dict."""
        self._start_emulators()

        ammeter_cfg = (self.config.get("ammeters") or {}).get(ammeter_type)
        if ammeter_cfg is None:
            raise ValueError(f"No config found for ammeter type: {ammeter_type!r}")

        sampling = (self.config.get("testing") or {}).get("sampling") or {}
        count = sampling.get("measurements_count") or 10
        duration = sampling.get("total_duration_seconds")
        frequency = sampling.get("sampling_frequency_hz") or 1.0

        port = ammeter_cfg["port"]
        command = ammeter_cfg["command"].encode("utf-8")
        range_cfg = ammeter_cfg.get("valid_range")
        valid_range = (float(range_cfg[0]), float(range_cfg[1])) if range_cfg else None

        range_str = f" | valid_range=[{valid_range[0]}, {valid_range[1]}]A" if valid_range else ""
        self.logger.info(
            f"Testing {ammeter_type} | port={port} | "
            f"{'duration=' + str(duration) + 's' if duration else 'count=' + str(count)} | "
            f"freq={frequency}Hz{range_str}"
        )

        samples, errors = self._collect_samples(port, command, count, duration, frequency, valid_range)

        if not samples:
            self.logger.error(f"No samples collected for {ammeter_type} — all requests failed")
            return {
                "ammeter_type": ammeter_type,
                "error": "no samples collected",
                "error_simulation": self._build_error_stats([], errors),
            }

        stats = self._analyze(samples)
        run_id = self._save_result(ammeter_type, samples, stats, errors)

        error_stats = self._build_error_stats(samples, errors)
        if error_stats:
            self.logger.info(
                f"{ammeter_type} errors → "
                f"{error_stats['failed']}/{error_stats['total_requests']} failed "
                f"({error_stats['actual_error_rate']:.0%}) | "
                f"by type: {error_stats['by_type']}"
            )

        self.logger.info(
            f"{ammeter_type} → mean={stats['mean']:.4f}A  "
            f"std={stats['std']:.4f}A  "
            f"min={stats['min']:.4f}A  max={stats['max']:.4f}A  "
            f"CV={stats['cv_percent']:.1f}%"
        )

        return {
            "run_id": run_id,
            "ammeter_type": ammeter_type,
            "samples": samples,
            "statistics": stats,
            "error_simulation": error_stats,
        }

    def run_all(self) -> Dict[str, Dict]:
        """Run tests for every ammeter defined in config, then visualize if enabled."""
        self._start_emulators()

        ammeter_types = list((self.config.get("ammeters") or {}).keys())
        results: Dict[str, Dict] = {}

        for ammeter_type in ammeter_types:
            self.logger.info(f"{'─' * 40}")
            results[ammeter_type] = self.run_test(ammeter_type)

        self.logger.info(f"{'─' * 40}")
        self._print_summary(results)

        viz_enabled = (
            (self.config.get("analysis") or {})
            .get("visualization", {})
            .get("enabled", False)
        )
        if viz_enabled:
            self._visualize(results)

        return results

    def _print_summary(self, results: Dict[str, Dict]) -> None:
        self.logger.info("SUMMARY")
        for name, result in results.items():
            if "error" in result and "statistics" not in result:
                self.logger.error(f"  {name}: {result['error']}")
                continue

            s = result["statistics"]
            err = result.get("error_simulation")
            err_str = (
                f" | errors={err['failed']}/{err['total_requests']} ({err['actual_error_rate']:.0%})"
                if err else ""
            )
            self.logger.info(
                f"  {name:10s} | mean={s['mean']:9.4f}A | "
                f"std={s['std']:8.4f}A | CV={s['cv_percent']:5.1f}%"
                f"{err_str}"
            )
