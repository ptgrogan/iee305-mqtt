"""Check TLS, student read access, rejected writes, and rejected logins on the broker."""

import argparse
from getpass import getpass
from pathlib import Path
import secrets
import ssl
import threading

import paho.mqtt.client as mqtt


def require_event(event, description):
    if not event.wait(10):
        raise RuntimeError(f"Timed out: {description}")


def connect(host, ca, username=None, password=None, expect_success=True):
    ready = threading.Event()
    result = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    if username is not None:
        client.username_pw_set(username, password)
    context = ssl.create_default_context(cafile=str(ca))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    client.tls_set_context(context)

    def on_connect(client, userdata, flags, reason_code, properties):
        result.append(not reason_code.is_failure)
        ready.set()

    client.on_connect = on_connect
    # Callbacks run on the background network thread after loop_start().
    client.connect(host, 8883, 30)
    client.loop_start()
    try:
        require_event(ready, f"CONNACK for {username or 'anonymous'}")
        if result[0] != expect_success:
            raise RuntimeError(f"Unexpected login result for {username or 'anonymous'}")
    except Exception:
        client.disconnect()
        client.loop_stop()
        raise
    return client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("--ca", type=Path, required=True)
    args = parser.parse_args()
    instructor_password = getpass("Instructor password: ")
    student_password = getpass("Student password: ")
    clients = []
    try:
        for username, password in [(None, None), ("student", secrets.token_urlsafe(32))]:
            clients.append(connect(args.host, args.ca, username, password, False))
        print("PASS: anonymous and incorrect-password logins rejected")

        instructor = connect(args.host, args.ca, "instructor", instructor_password)
        clients.append(instructor)
        student = connect(args.host, args.ca, "student", student_password)
        clients.append(student)

        topic = "iee305/l20/access-check/" + secrets.token_hex(8)
        payload = b'{"source":"access-check","value":305}'
        subscribed = threading.Event()
        received = threading.Event()
        denied = threading.Event()
        failures = []

        def on_subscribe(client, userdata, mid, reason_codes, properties):
            if any(code.is_failure for code in reason_codes):
                failures.append("Student subscription was refused")
            subscribed.set()

        def on_message(client, userdata, message):
            if message.topic == topic and message.payload == payload:
                received.set()

        def on_publish(client, userdata, mid, reason_code, properties):
            # MQTT 5 QoS 1 makes an authorization failure observable in PUBACK.
            if reason_code.value != 135:  # 0x87: Not authorized
                failures.append(f"Student publish was not denied: {reason_code}")
            denied.set()

        student.on_subscribe = on_subscribe
        student.on_message = on_message
        student.on_publish = on_publish
        student.subscribe(topic, qos=1)
        require_event(subscribed, "student SUBACK")
        if failures:
            raise RuntimeError("; ".join(failures))
        message = instructor.publish(topic, payload, qos=1, retain=False)
        message.wait_for_publish(timeout=10)
        require_event(received, "instructor message received by student")
        print("PASS: instructor can publish and student can receive over verified TLS")
        student.publish(topic, b'{"source":"student-write-test"}', qos=1, retain=False)
        require_event(denied, "student publish rejection")
        if failures:
            raise RuntimeError("; ".join(failures))
        print("PASS: student publish denied (MQTT 5 Not authorized)")
    finally:
        for client in clients:
            client.disconnect()
            client.loop_stop()


if __name__ == "__main__":
    main()
