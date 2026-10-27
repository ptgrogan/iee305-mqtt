"""Chat with the class through the IEE 305 MQTT broker. Type a line and press Enter."""

import argparse
from getpass import getpass
import json
import sys
import threading

import certifi
import paho.mqtt.client as mqtt

BROKER = "mqtt.iee305.code-lab.org"
PORT = 443  # MQTT over secure WebSockets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Name shown to classmates")
    parser.add_argument("--room", default="lobby")
    parser.add_argument("--host", default=BROKER, help="Broker hostname (default: %(default)s)")
    args = parser.parse_args()
    topic = f"iee305/l19/class/chat/{args.room}"
    password = getpass("Class MQTT password: ")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets",
                         protocol=mqtt.MQTTv5)
    client.username_pw_set("student", password)
    client.tls_set(ca_certs=certifi.where())
    # Last Will: the broker publishes this for us if we vanish without disconnecting,
    # for example if the network drops or the terminal window is closed.
    client.will_set(topic, json.dumps({"from": args.name, "text": "(lost connection)"}), qos=1)

    connected = threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"Broker refused the login: {reason_code}. Check the class password.")
            client.disconnect()
        else:
            # Subscribing here means a reconnect subscribes again automatically.
            client.subscribe(topic, qos=1)
            connected.set()

    def on_message(client, userdata, message):
        try:
            chat = json.loads(message.payload)
            print(f"[{chat['from']}] {chat['text']}", flush=True)
        except (ValueError, KeyError, TypeError):
            print(f"(not chat JSON) {message.payload!r}", flush=True)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, port=PORT, keepalive=60)
    # loop_start() runs the network loop on a background thread, which leaves
    # this main thread free to wait for keyboard input.
    client.loop_start()
    if not connected.wait(10):
        client.loop_stop()
        sys.exit("Could not join the chat.")
    print(f"Joined {topic} as {args.name}. Press Ctrl+C to leave.")
    client.publish(topic, json.dumps({"from": args.name, "text": "(joined)"}), qos=1)
    try:
        for line in sys.stdin:
            if line.strip():
                client.publish(topic, json.dumps({"from": args.name, "text": line.strip()}), qos=1)
    except KeyboardInterrupt:
        pass
    client.publish(topic, json.dumps({"from": args.name, "text": "(left)"}), qos=1).wait_for_publish(5)
    client.disconnect()  # A normal disconnect cancels the Last Will.
    client.loop_stop()


if __name__ == "__main__":
    main()
