"""Print every message the IEE 305 class broker delivers on a topic."""

import argparse
from datetime import datetime, timezone
from getpass import getpass
import ssl
import sys

import certifi
import paho.mqtt.client as mqtt

BROKER = "mqtt.iee305.code-lab.org"
PORT = 443  # MQTT over secure WebSockets; passes networks that block port 8883


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="iee305/l20/zigbee2mqtt/#",
                        help="Topic filter; + and # are wildcards (default: %(default)s)")
    parser.add_argument("--host", default=BROKER, help="Broker hostname (default: %(default)s)")
    args = parser.parse_args()
    password = getpass("Class MQTT password: ")

    # An empty client ID lets the broker assign a unique ID to each student.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets",
                         protocol=mqtt.MQTTv5)
    client.username_pw_set("student", password)
    # Verify the broker's Let's Encrypt certificate using certifi's public CA list.
    client.tls_set(ca_certs=certifi.where())

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"Broker refused the login: {reason_code}. Check the class password.")
            client.disconnect()
            return
        print(f"Connected; subscribing to {args.topic}", flush=True)
        client.subscribe(args.topic, qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            print(f"Subscription refused: {reason_codes[0]}. Check the topic.")
            client.disconnect()

    def on_message(client, userdata, message):
        received_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        payload = message.payload.decode("utf-8", errors="replace")
        print(f"{received_at} retain={message.retain} qos={message.qos} "
              f"{message.topic} {payload}", flush=True)

    def on_disconnect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"Connection lost ({reason_code}); reconnecting...", flush=True)

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    try:
        client.connect(args.host, port=PORT, keepalive=60)
    except ssl.SSLCertVerificationError as err:
        sys.exit(f"TLS certificate check failed: {err.verify_message}. "
                 "Check your computer's clock, then run: pip install --upgrade certifi")
    except OSError as err:
        sys.exit(f"Could not reach {args.host}:{PORT} ({err}). Check your network connection.")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nDisconnected.")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
