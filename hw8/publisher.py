"""Publish HW-8 simulated observations continuously; no physical devices required."""

import json
import logging
import os
from pathlib import Path
import signal
import threading
import time

import paho.mqtt.client as mqtt

from scenario import BASE_TOPIC, DEVICES, INTERVAL_SECONDS, SAMPLES_PER_CYCLE, make_reading


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    password = Path(os.environ["MQTT_PASSWORD_FILE"]).read_text().strip()
    ready = threading.Event()
    stopping = threading.Event()
    rejected = threading.Event()

    def stop(signum, frame):
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            logging.error("Broker login refused: %s", reason_code)
            rejected.set()
        else:
            ready.set()
            logging.info("Connected to the HW-8 broker")

    def on_disconnect(client, userdata, flags, reason_code, properties):
        ready.clear()

    def on_publish(client, userdata, mid, reason_code, properties):
        if reason_code.is_failure:
            logging.error("Publication rejected: %s", reason_code)
            rejected.set()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.username_pw_set(os.environ.get("MQTT_USERNAME", "hw8-publisher"), password)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish
    client.reconnect_delay_set(min_delay=1, max_delay=15)
    client.connect_async(os.environ.get("MQTT_HOST", "mosquitto"),
                         int(os.environ.get("MQTT_PORT", "1883")), keepalive=30)
    client.loop_start()
    previous_tick = None
    try:
        while not stopping.is_set():
            if rejected.is_set():
                raise RuntimeError("Check the HW-8 publisher credential and topic ACL")
            if not ready.wait(timeout=1):
                continue
            tick = int(time.time() // INTERVAL_SECONDS)
            if tick == previous_tick:
                stopping.wait(0.2)
                continue
            cycle_id, index = divmod(tick, SAMPLES_PER_CYCLE)
            for device_id in DEVICES:
                reading = make_reading(device_id, cycle_id, index + 1)
                info = client.publish(f"{BASE_TOPIC}/{device_id}",
                                      json.dumps(reading, allow_nan=False), qos=1, retain=True)
                info.wait_for_publish(timeout=5)
                if not info.is_published() or rejected.is_set():
                    raise RuntimeError("An HW-8 publication was not acknowledged successfully")
            Path("/tmp/hw8-heartbeat").touch()
            if index == 0:
                logging.info("Started cycle %s; 24 samples per device at 5-second intervals", cycle_id)
            previous_tick = tick
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
