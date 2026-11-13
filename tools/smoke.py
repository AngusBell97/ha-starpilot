"""Read a real comma with the integration's own client and print what each entity would show.

Usage: python tools/smoke.py <comma address> [port]
Reads only; add --write-check to also send the drive state it already has (a no-op) to prove writes are accepted.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.starpilot.api import GalaxyClient  # noqa: E402
from custom_components.starpilot.binary_sensor import BINARY_SENSORS  # noqa: E402
from custom_components.starpilot.api import GalaxyApiError  # noqa: E402
from custom_components.starpilot.coordinator import SECTIONS, external_gpu, trim  # noqa: E402
from custom_components.starpilot.sensor import GPU_SENSORS, SENSORS  # noqa: E402


async def main() -> int:
    arguments = [value for value in sys.argv[1:] if not value.startswith("--")]
    if not arguments:
        print(__doc__)
        return 2
    host, port = arguments[0], int(arguments[1]) if len(arguments) > 1 else 8082
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        client = GalaxyClient(session, host, port)
        data = {}
        for section, (path, _) in SECTIONS.items():
            try:
                value = trim(section, await client.async_get(path))
            except GalaxyApiError as error:
                print(f"skip {path}: {error}")
                continue
            data[section] = value
            print(f"read {path}")
        print()
        gpu = external_gpu(data)
        for description in (*SENSORS, *(GPU_SENSORS if gpu else ())):
            unit = description.native_unit_of_measurement or ""
            print(f"sensor         {description.key:34} {description.value_fn(data)!s:>28} {unit}")
        for description in BINARY_SENSORS:
            print(f"binary_sensor  {description.key:34} {description.is_on_fn(data)!s:>28}")
        print(f"select         {'drive_mode':34} {data['drive_state'].get('mode')!s:>28}")
        if "--write-check" in sys.argv:
            mode = data["drive_state"]["mode"]
            result = await client.async_set_drive_mode(mode)
            print(f"\nwrite accepted: drive state stays {result.get('mode')}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
