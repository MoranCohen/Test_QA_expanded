import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.testing.test_framework import AmmeterTestFramework


def main():
    framework = AmmeterTestFramework()
    results = framework.run_all()

    print("\n=== Final Results ===")
    for ammeter_type, result in results.items():
        if "error" in result:
            print(f"{ammeter_type}: ERROR — {result['error']}")
            continue
        s = result["statistics"]
        print(
            f"{ammeter_type:10s} | "
            f"mean={s['mean']:9.4f}A | "
            f"std={s['std']:8.4f}A | "
            f"min={s['min']:9.4f}A | "
            f"max={s['max']:9.4f}A | "
            f"CV={s['cv_percent']:5.1f}%"
        )


if __name__ == "__main__":
    main()
