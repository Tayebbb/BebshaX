"""Compatibility notice for the retired local-inference demo preflight."""

if __name__ == "__main__":
    raise SystemExit(
        "This local-inference demo preflight is retired. Use scripts/release_preflight.py. "
        "Historical demo artifacts are retained; cached examples do not certify offline live inference."
    )