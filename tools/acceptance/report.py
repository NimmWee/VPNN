"""Calculate acceptance metrics from a synthetic fixture, entirely offline."""
import argparse
import json
import math
from pathlib import Path


def summarize(data):
    fields = {
        "source", "seconds", "payload_bytes", "cpu_usec_delta",
        "baseline_ram_bytes", "load_ram_bytes",
    }
    if not isinstance(data, dict) or data.keys() != fields or data["source"] != "synthetic":
        raise ValueError("expected only the synthetic fixture fields")

    seconds = data["seconds"]
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("seconds must be finite and positive")

    payload = data["payload_bytes"]
    if not isinstance(payload, list) or not payload:
        raise ValueError("expected byte counts for at least one client")
    counters = [*payload, data["cpu_usec_delta"], data["baseline_ram_bytes"], data["load_ram_bytes"]]
    if any(type(value) is not int or value < 0 for value in counters):
        raise ValueError("counters must be nonnegative integers")

    return {
        "schema": 1,
        "source": "synthetic",
        "egress": "synthetic",
        "field_verdict": "NOT TESTED",
        "clients": len(payload),
        "goodput_mbps": sum(payload) * 8 / seconds / 1_000_000,
        "cpu_cores": data["cpu_usec_delta"] / seconds / 1_000_000,
        "ram_delta_mib": (data["load_ram_bytes"] - data["baseline_ram_bytes"]) / 2**20,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    try:
        result = summarize(json.loads(args.fixture.read_text(encoding="utf-8")))
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, OverflowError):
        parser.error("invalid or unreadable synthetic fixture")


if __name__ == "__main__":
    main()
