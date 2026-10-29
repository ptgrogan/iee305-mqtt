"""Check the class broker: TLS, the browser page, logins, and the L-19 and L-20 topic permissions.

Every test message is non-retained and uses a unique .../access-check/... topic,
outside the Zigbee command path.
"""

import argparse
from getpass import getpass
import secrets
import ssl
import threading
import urllib.request

import certifi
import paho.mqtt.client as mqtt

BROKER = "mqtt.iee305.code-lab.org"
PORTS = {"websockets": 443, "tcp": 8883}
NOT_AUTHORIZED = 135  # MQTT 5 reason code 0x87


def require_event(event, description):
    if not event.wait(10):
        raise RuntimeError(f"Timed out: {description}")


def check_page(args):
    context = ssl.create_default_context(cafile=args.ca)
    with urllib.request.urlopen(f"https://{args.host}/", context=context, timeout=10) as response:
        if b"<title>IEE 305 MQTT</title>" not in response.read():
            raise RuntimeError(f"https://{args.host}/ did not return the browser page")


def connect(args, transport, username=None, password=None, expect_success=True):
    ready = threading.Event()
    result = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport=transport,
                         protocol=mqtt.MQTTv5)
    if username is not None:
        client.username_pw_set(username, password)
    if transport == "websockets" and username == "instructor":
        # Zigbee2MQTT requests path / where Paho requests /mqtt; nginx must
        # forward both to the broker rather than serve the page.
        client.ws_set_options(path="/")
    client.tls_set(ca_certs=args.ca)

    def on_connect(client, userdata, flags, reason_code, properties):
        result.append(not reason_code.is_failure)
        ready.set()

    client.on_connect = on_connect
    # Callbacks run on the background network thread after loop_start().
    client.connect(args.host, PORTS[transport], 30)
    client.loop_start()
    try:
        require_event(ready, f"CONNACK for {username or 'anonymous'}")
        if result[0] != expect_success:
            raise RuntimeError(f"Unexpected login result for {username or 'anonymous'}")
    except Exception:
        client.disconnect()
        client.loop_stop()
        raise
    if not expect_success:
        # Stop paho's automatic reconnect attempts with the rejected credentials.
        client.disconnect()
        client.loop_stop()
        return None
    return client


def expect_delivery(publisher, subscriber, topic):
    payload = secrets.token_hex(8).encode()
    subscribed = threading.Event()
    received = threading.Event()
    refused = []

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        refused.extend(code for code in reason_codes if code.is_failure)
        subscribed.set()

    def on_message(client, userdata, message):
        if message.topic == topic and message.payload == payload:
            received.set()

    subscriber.on_subscribe = on_subscribe
    subscriber.on_message = on_message
    subscriber.subscribe(topic, qos=1)
    require_event(subscribed, f"SUBACK for {topic}")
    if refused:
        raise RuntimeError(f"Subscription to {topic} refused: {refused[0]}")
    publisher.publish(topic, payload, qos=1, retain=False)
    require_event(received, f"delivery on {topic}")
    subscriber.unsubscribe(topic)


def expect_denied(client, topic):
    acknowledged = threading.Event()
    codes = []

    def on_publish(client, userdata, mid, reason_code, properties):
        codes.append(reason_code)
        acknowledged.set()

    # MQTT 5 QoS 1 makes an authorization failure observable in PUBACK.
    client.on_publish = on_publish
    client.publish(topic, b'{"source":"access-check"}', qos=1, retain=False)
    require_event(acknowledged, f"PUBACK for {topic}")
    client.on_publish = None
    if codes[0].value != NOT_AUTHORIZED:
        raise RuntimeError(f"Publish to {topic} was not denied: {codes[0]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", default=BROKER)
    parser.add_argument("--ca", default=certifi.where(),
                        help="CA bundle (default: certifi's public CAs, which include Let's Encrypt)")
    args = parser.parse_args()
    instructor_password = getpass("Instructor password: ")
    student_password = getpass("Student password: ")

    check_page(args)
    print("PASS: browser page served over HTTPS on port 443")

    for username, password in [(None, None), ("student", secrets.token_urlsafe(32))]:
        connect(args, "websockets", username, password, expect_success=False)
    print("PASS: anonymous and incorrect-password logins rejected")

    for transport, port in PORTS.items():
        clients = []
        try:
            for username, password in [("instructor", instructor_password),
                                       ("student", student_password),
                                       ("student", student_password)]:
                clients.append(connect(args, transport, username, password))
            instructor, student, classmate = clients
            run = secrets.token_hex(8)
            expect_delivery(instructor, student, f"iee305/l20/access-check/{run}")
            expect_denied(student, f"iee305/l20/access-check/{run}")
            expect_delivery(student, classmate, f"iee305/l19/class/access-check/{run}")
            expect_delivery(instructor, student, f"iee305/l19/instructor/access-check/{run}")
            expect_denied(student, f"iee305/l19/instructor/access-check/{run}")
        finally:
            for client in clients:
                client.disconnect()
                client.loop_stop()
        print(f"PASS: {transport} on port {port}: L-20 read-only, L-19 class publishing, "
              "instructor-only broadcasts")


if __name__ == "__main__":
    main()
