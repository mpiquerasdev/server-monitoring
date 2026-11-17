#!/usr/bin/env python3
"""Report an unexpected systemd monitoring unit failure."""

import sys

from healthcheck import send_message


if __name__ == "__main__":
    unit = sys.argv[1] if len(sys.argv) > 1 else "unknown unit"
    send_message(f"🚨 CRÍTICO: fallo en {unit}\nRevisar: journalctl -u {unit}")
