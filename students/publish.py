"""Publish one message to the IEE 305 class broker, then disconnect."""

import argparse
from getpass import getpass

import certifi
import paho.mqtt.client as mqtt

BROKER = "mqtt.iee305.code-lab.org"
PORT = 443  # MQTT over secure WebSockets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", help="For example: iee305/l19/class/YOUR_ASURITE/hello")
    parser.add_argument("message")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1)
    parser.add_argument("--retain", action="store_true",
                        help="Ask the broker to keep this as the topic's last known value")
    parser.add_argument("--username", default="student")
    parser.add_argument("--host", default=BROKER, help="Broker hostname (default: %(default)s)")
    args = parser.parse_args()
    password = getpass(f"MQTT password for {args.username}: ")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets",
                         protocol=mqtt.MQTTv5)
    client.username_pw_set(args.username, password)
    client.tls_set(ca_certs=certifi.where())

    # Paho is event driven: publish once the broker accepts the login, and
    # disconnect once the broker acknowledges the message.
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"Broker refused the login: {reason_code}. Check the password.")
            client.disconnect()
            return
        client.publish(args.topic, args.message, qos=args.qos, retain=args.retain)

    def on_publish(client, userdata, mid, reason_code, properties):
        # With QoS 1 or 2 this reports the broker's answer, e.g. "Not authorized".
        print(f"Broker response to {args.topic} (qos={args.qos}, retain={args.retain}): "
              f"{reason_code}")
        client.disconnect()

    client.on_connect = on_connect
    client.on_publish = on_publish
    client.connect(args.host, port=PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
