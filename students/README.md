# Lecture 20 MQTT subscriber

The instructor supplies the broker hostname, the class password for username `student`, and a file named `ca.crt`. Put `ca.crt` in this folder. You need Python 3.10 or newer; you do not need Docker, an AWS account, or a Zigbee dongle.

On Windows, open PowerShell in this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe subscribe.py BROKER_HOSTNAME
```

On Linux or macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python subscribe.py BROKER_HOSTNAME
```

Replace `BROKER_HOSTNAME` with the instructor's hostname, without `mqtts://` or a port. Enter the class password at the hidden prompt. Stop with Ctrl+C.

The output shows receipt time in UTC, the retained-message flag, QoS, the MQTT topic, and the payload. The default subscription `iee305/l20/zigbee2mqtt/#` includes all lecture devices and bridge metadata. Subscribe to one sensor using:

```text
subscribe.py BROKER_HOSTNAME --topic iee305/l20/zigbee2mqtt/lecture_sensor
```

Use the same Python command prefix as above. Your account can subscribe but cannot publish. A quiet sensor may only report periodically or when its value changes. Keep the supplied CA certificate and certificate verification enabled.

During the demonstration, identify the publisher, broker, topic, and subscribers. Compare a single-device topic with the wildcard subscription, then explain whether two students receive the same message and whether the device knows who subscribed.
