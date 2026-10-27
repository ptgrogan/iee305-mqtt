"""Delete retained messages under a topic filter (default: everything students can write).

The broker sends retained messages immediately after a subscription; publishing an
empty retained payload to a topic removes its retained message.
"""

import argparse
from getpass import getpass
import sys
import threading
import time

import certifi
import paho.mqtt.client as mqtt

BROKER = "mqtt.iee305.code-lab.org"
PORT = 443


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="iee305/l19/class/#")
    parser.add_argument("--dry-run", action="store_true", help="List the topics only")
    parser.add_argument("--host", default=BROKER)
    parser.add_argument("--ca", default=certifi.where())
    args = parser.parse_args()
    password = getpass("Instructor password: ")

    retained = set()
    subscribed = threading.Event()
    refusal = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets",
                         protocol=mqtt.MQTTv5)
    client.username_pw_set("instructor", password)
    client.tls_set(ca_certs=args.ca)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            refusal.append(reason_code)
            subscribed.set()
            client.disconnect()
            return
        client.subscribe(args.topic, qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        refusal.extend(code for code in reason_codes if code.is_failure)
        subscribed.set()

    def on_message(client, userdata, message):
        if message.retain and message.payload:
            retained.add(message.topic)

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect(args.host, PORT, 30)
    client.loop_start()
    if not subscribed.wait(10) or refusal:
        client.loop_stop()
        reason = refusal[0] if refusal else "timed out"
        sys.exit(f"Could not read {args.topic} ({reason}). Check the instructor password.")
    time.sleep(3)  # Collect the retained messages the broker sends after SUBACK.
    client.unsubscribe(args.topic)
    for topic in sorted(retained):
        print(topic)
        if not args.dry_run:
            client.publish(topic, b"", qos=1, retain=True).wait_for_publish(10)
    action = "Found" if args.dry_run else "Cleared"
    print(f"{action} {len(retained)} retained message(s) under {args.topic}")
    client.disconnect()
    client.loop_stop()


if __name__ == "__main__":
    main()
