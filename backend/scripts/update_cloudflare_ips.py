"""Rewrite app/cloudflare_ips.txt from Cloudflare's published IP ranges. Commit the result.

    python scripts/update_cloudflare_ips.py
"""

import ipaddress
import urllib.request
from datetime import date
from pathlib import Path

SOURCES = ("https://www.cloudflare.com/ips-v4", "https://www.cloudflare.com/ips-v6")
TARGET = Path(__file__).resolve().parents[1] / "app" / "cloudflare_ips.txt"


def fetch(url: str) -> list[str]:
    with urllib.request.urlopen(url, timeout=20) as r:
        lines = [line.strip() for line in r.read().decode().splitlines() if line.strip()]
    for line in lines:
        ipaddress.ip_network(line)  # refuse to write anything that isn't a CIDR
    return lines


def main() -> None:
    ranges = [cidr for url in SOURCES for cidr in fetch(url)]
    header = [
        "# Cloudflare's published edge IP ranges, trusted as proxies when CLOUDFLARE_PROXY=true.",
        f"# Source: {SOURCES[0]} and {SOURCES[1]} (fetched {date.today().isoformat()}).",
        "# Refresh with: python scripts/update_cloudflare_ips.py",
    ]
    TARGET.write_text("\n".join(header + ranges) + "\n")
    print(f"{len(ranges)} ranges → {TARGET}")


if __name__ == "__main__":
    main()
