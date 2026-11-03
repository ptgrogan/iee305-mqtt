"""Supplied collection support for capturing one complete HW-8 cycle."""

import json
import time


def collect_cycle(messages, timeout=270):
    """Read a growing message list; exclude retained and repeated observations."""
    deadline = time.monotonic() + timeout
    devices = ("REF-01", "REF-02", "REF-03")
    selected_cycle = None
    collected = {}
    position = 0
    while time.monotonic() < deadline:
        snapshot = messages.copy()
        for message in snapshot[position:]:
            if message["retained"]:
                continue
            try:
                data = json.loads(message["text"])
                device = data["device_id"]
                cycle = data["cycle_id"]
                sample = data["sample_id"]
            except (ValueError, KeyError, TypeError):
                continue
            if (device not in devices or data.get("scenario_version") != "hw8-v1"
                    or message["topic"] != f"iee305/hw8/warehouse/{device}"
                    or not 1 <= sample <= 24):
                continue
            if sample == 1 and (selected_cycle is None or cycle > selected_cycle):
                selected_cycle = cycle
                collected = {}
            if selected_cycle is not None and cycle == selected_cycle:
                collected[(device, sample)] = message
                if len(collected) == 72:
                    print("Captured cycle:", selected_cycle)
                    print("Unique live observations:", len(collected), "(24 per device)")
                    return [collected[key] for key in sorted(collected)]
        position = len(snapshot)
        time.sleep(0.25)
    raise TimeoutError(
        "No complete HW-8 cycle arrived. Check the topic and connection, then retry. "
        "If the service is unavailable, keep this error as Part B evidence and "
        "contact the instructor."
    )
