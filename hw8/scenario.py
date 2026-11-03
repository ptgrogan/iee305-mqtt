"""Fixed HW-8 cold-storage episode; values are synthetic teaching data."""

from datetime import datetime, timezone

DEVICES = ("REF-01", "REF-02", "REF-03")
VERSION = "hw8-v1"
BASE_TOPIC = "iee305/hw8/warehouse"
INTERVAL_SECONDS = 5
SAMPLES_PER_CYCLE = 24
CYCLE_SECONDS = INTERVAL_SECONDS * SAMPLES_PER_CYCLE

TEMPERATURES = {
    "REF-01": [4.0, 4.1, 4.2, 4.3, 4.4, 4.5, 4.4, 4.3, 4.2, 4.1, 4.0, 4.1,
               4.2, 4.3, 4.4, 4.5, 4.6, 4.5, 4.4, 4.3, 4.2, 4.1, 4.0, 4.0],
    "REF-02": [4.0, 4.2, 4.3, 4.4, 4.5, 4.6, 5.0, 6.0, 7.5, 8.5, 9.5, 10.5,
               11.0, 10.5, 9.5, 8.5, 7.5, 6.5, 5.5, 5.0, 4.5, 4.2, 4.1, 4.0],
    "REF-03": [1.0, 0.8, 0.5, 0.2, 0.0, 0.3, 0.6, 0.8, 1.0, 1.2, 1.4, 1.5,
               1.4, 1.3, 1.2, 1.1, 1.0, 0.9, 0.8, 0.9, 1.0, 1.1, 1.0, 1.0],
}

HUMIDITIES = {
    "REF-01": [54.0 + (i % 5) for i in range(24)],
    "REF-02": [55.0, 55.0, 56.0, 56.0, 57.0, 58.0, 62.0, 66.0, 68.0, 70.0,
               69.0, 68.0, 66.0, 64.0, 62.0, 60.0, 59.0, 58.0, 57.0, 56.0,
               56.0, 55.0, 55.0, 55.0],
    "REF-03": [48.0, 49.0, 50.0, 51.0, 50.0, 49.0, 48.0, 49.0,
               None, None, None, None, 50.0, 51.0, 52.0, 51.0,
               50.0, 49.0, 48.0, 49.0, 50.0, 51.0, 50.0, 49.0],
}


def make_reading(device_id, cycle_id, sample_id):
    """One observation, identified by (device_id, cycle_id, sample_id)."""
    if device_id not in DEVICES or not 1 <= sample_id <= SAMPLES_PER_CYCLE:
        raise ValueError("Unknown device or sample_id outside 1..24")
    index = sample_id - 1
    observed_at = datetime.fromtimestamp(
        cycle_id * CYCLE_SECONDS + index * INTERVAL_SECONDS, timezone.utc
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "device_id": device_id,
        "source": "simulated",
        "scenario_version": VERSION,
        "cycle_id": cycle_id,
        "sample_id": sample_id,
        "observed_at": observed_at,
        "temperature": TEMPERATURES[device_id][index],
        "humidity": HUMIDITIES[device_id][index],
        "door_open": device_id == "REF-02" and 7 <= sample_id <= 12,
    }


def cycle_readings(cycle_id):
    for sample_id in range(1, SAMPLES_PER_CYCLE + 1):
        for device_id in DEVICES:
            yield make_reading(device_id, cycle_id, sample_id)
