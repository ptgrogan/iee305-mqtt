"""Receive lecture telemetry. The instructor supplies ca.crt and the class login."""

import argparse
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
import ssl

import paho.mqtt.client as mqtt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="Broker hostname, without mqtts:// or a port")
    parser.add_argument("--ca", type=Path, default=Path(__file__).with_name("ca.crt"))
    parser.add_argument("--topic", default="iee305/l20/zigbee2mqtt/#")
    args = parser.parse_args()
    password = getpass("Class MQTT password: ")

    # An empty client ID lets the broker assign a unique ID to each student.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.username_pw_set("student", password)
    context = ssl.create_default_context(cafile=str(args.ca))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    client.tls_set_context(context)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            raise RuntimeError(f"Connection refused: {reason_code}")
        print(f"Connected; subscribing to {args.topic}", flush=True)
        client.subscribe(args.topic, qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            raise RuntimeError(f"Subscription refused: {reason_codes}")

    def on_message(client, userdata, message):
        received_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        payload = message.payload.decode("utf-8", errors="replace")
        print(f"{received_at} retain={message.retain} qos={message.qos} "
              f"{message.topic} {payload}", flush=True)

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect(args.host, port=8883, keepalive=60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nDisconnected.")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
