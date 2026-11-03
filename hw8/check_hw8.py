"""Check the HW-8 simulator as a student: live data, a complete cycle, and subscriber-only access.

The access check publishes one non-retained message to a unique
iee305/hw8/access-check/... topic; it never changes retained device data.
"""

import argparse
from datetime import datetime, timezone
from getpass import getpass
import json
import secrets
import threading

import certifi
import paho.mqtt.client as mqtt

from capture import collect_cycle
from scenario import BASE_TOPIC, DEVICES, make_reading

BROKER = "mqtt.iee305.code-lab.org"
PORT = 443  # MQTT over secure WebSockets, as students connect
NOT_AUTHORIZED = 135  # MQTT 5 reason code 0x87


def require_event(event, description):
    if not event.wait(10):
        raise RuntimeError(f"Timed out: {description}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=BROKER)
    parser.add_argument("--ca", default=certifi.where(),
                        help="CA bundle (default: certifi's public CAs, which include Let's Encrypt)")
    args = parser.parse_args()
    ready = threading.Event()
    acknowledged = threading.Event()
    messages = []
    login = []
    grants = []
    replies = []

    def on_connect(client, userdata, flags, reason_code, properties):
        login.append(reason_code)
        if not reason_code.is_failure:
            client.subscribe(f"{BASE_TOPIC}/+", qos=1)
        else:
            ready.set()

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        grants.extend(reason_codes)
        ready.set()

    def on_message(client, userdata, message):
        messages.append({"topic": message.topic,
                         "text": message.payload.decode("utf-8", errors="replace"),
                         "retained": message.retain,
                         "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})

    def on_publish(client, userdata, mid, reason_code, properties):
        replies.append(reason_code)
        acknowledged.set()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets",
                         protocol=mqtt.MQTTv5)
    client.username_pw_set("student", getpass("Student password: "))
    client.tls_set(ca_certs=args.ca)
    client.on_connect, client.on_subscribe = on_connect, on_subscribe
    client.on_message, client.on_publish = on_message, on_publish
    client.connect(args.host, PORT)
    client.loop_start()
    try:
        require_event(ready, "student login and subscription")
        if login[0].is_failure:
            raise RuntimeError(f"Student login refused: {login[0]}")
        if not grants or any(code.is_failure for code in grants):
            raise RuntimeError(f"Subscription refused: {grants}")
        captured = collect_cycle(messages)
        readings = [json.loads(message["text"]) for message in captured]
        for data in readings:
            if data != make_reading(data["device_id"], data["cycle_id"], data["sample_id"]):
                raise RuntimeError(f"Observation differs from the scenario: {data}")
        if {data["device_id"] for data in readings} != set(DEVICES):
            raise RuntimeError("The captured cycle is missing a device")
        retained = {json.loads(m["text"])["device_id"] for m in messages
                    if m["retained"] and m["topic"].startswith(BASE_TOPIC + "/")}
        if retained != set(DEVICES):
            raise RuntimeError(f"Expected one retained current value per device, got {sorted(retained)}")
        print("PASS: current retained states and a complete scenario cycle match the reference")

        denied_topic = f"iee305/hw8/access-check/{secrets.token_hex(6)}"
        ready.clear()
        client.subscribe(denied_topic, qos=1)
        require_event(ready, f"SUBACK for {denied_topic}")
        # MQTT 5 QoS 1 makes an authorization failure observable in PUBACK.
        info = client.publish(denied_topic, "hw8-authorization-check", qos=1, retain=False)
        require_event(acknowledged, f"PUBACK for {denied_topic}")
        if replies[-1].value != NOT_AUTHORIZED:
            raise RuntimeError(f"Student publication to HW-8 was not denied: {replies[-1]}")
        info.wait_for_publish(timeout=5)
        if any(m["topic"] == denied_topic for m in messages):
            raise RuntimeError("Forbidden publication reached the subscriber")
        print("PASS: student can subscribe but cannot publish under iee305/hw8/")
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
