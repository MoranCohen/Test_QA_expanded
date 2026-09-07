import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.testing.test_framework import AmmeterTestFramework

_logger = logging.getLogger(__name__)


def main() -> None:
    framework = AmmeterTestFramework()
    results = framework.run_all()

    _logger.info("=== Final Results ===")
    for ammeter_type, result in results.items():
        if "error" in result:
            _logger.error(f"{ammeter_type}: ERROR — {result['error']}")
            continue
        s = result["statistics"]
        _logger.info(
            f"{ammeter_type:10s} | "
            f"mean={s['mean']:9.4f}A | "
            f"std={s['std']:8.4f}A | "
            f"min={s['min']:9.4f}A | "
            f"max={s['max']:9.4f}A | "
            f"CV={s['cv_percent']:5.1f}%"
        )


if __name__ == "__main__":
    main()
