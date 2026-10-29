# IEE 305 MQTT student scripts

Your instructor shares the class password for username `student` through Canvas. The same password works for Lectures 19 and 20. The scripts connect to the class broker at `mqtt.iee305.code-lab.org` using MQTT over secure WebSockets on port 443, which works on networks that block MQTT's usual port 8883. You need Git and Python 3.10 or newer; you do not need Docker, an AWS account, a certificate file, or a Zigbee dongle.

## Setup (once)

On Windows, open PowerShell:

```powershell
git clone https://github.com/ptgrogan/iee305-mqtt.git
Set-Location iee305-mqtt/students
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On Linux or macOS:

```bash
git clone https://github.com/ptgrogan/iee305-mqtt.git
cd iee305-mqtt/students
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

If you already cloned the repository, run `git pull` in it instead. In the commands below, `python` stands for `.\.venv\Scripts\python.exe` on Windows or `.venv/bin/python` on Linux/macOS, run from this `students` folder. Each script asks for the password at a hidden prompt, where nothing appears as you type. Stop a running script with Ctrl+C.

## Lecture 19: publish and subscribe

You may publish anywhere under `iee305/l19/class/`; by convention, use your ASURITE ID, as in `iee305/l19/class/YOUR_ASURITE/...`. You can subscribe to everything under `iee305/l19/`, including the instructor's broadcasts under `iee305/l19/instructor/`.

Watch everything in the exercise, in one terminal:

```text
python subscribe.py --topic "iee305/l19/#"
```

Publish from a second terminal:

```text
python publish.py iee305/l19/class/YOUR_ASURITE/hello "Hello from YOUR_ASURITE"
python publish.py iee305/l19/class/YOUR_ASURITE/status "studying" --retain
python publish.py iee305/l19/class/YOUR_ASURITE/hello "QoS 0 test" --qos 0
```

`publish.py` prints the broker's response. `Success` and `No matching subscribers` both mean the broker accepted the message; `Not authorized` means your account may not publish to that topic. Subscribe with the `+` wildcard to collect one topic level from everyone: `--topic "iee305/l19/class/+/hello"`.

Chat with classmates. Type a line and press Enter to send it:

```text
python chat.py YOUR_NAME
python chat.py YOUR_NAME --room team3
```

Close the chat window instead of pressing Ctrl+C, and the others see `(lost connection)`: the broker publishes your **Last Will** message when a client disappears without disconnecting.

### Browser client

Open <https://mqtt.iee305.code-lab.org/?lecture=19> and log in as `student` with the same class password. The page is another MQTT client, written in JavaScript with the MQTT.js library. It connects over secure WebSockets on port 443, like the Python scripts, and the broker applies the same permissions. You can watch a topic filter, publish with any QoS and the retain flag, and chat with classmates who use `chat.py`. Closing the tab while in a chat room triggers your Last Will. Its source, [`ec2/web/app.js`](../ec2/web/app.js), is short and commented: compare its `connect`, `subscribe`, `publish`, and `message` handling with the Python template below.

### Writing your own client

Start from this template. Each script in this folder is a commented, slightly longer version of it.

```python
from getpass import getpass

import certifi
import paho.mqtt.client as mqtt

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets",
                     protocol=mqtt.MQTTv5)
client.username_pw_set("student", getpass("Class MQTT password: "))
client.tls_set(ca_certs=certifi.where())  # verify the broker's certificate

def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected:", reason_code)
    client.subscribe("iee305/l19/class/#")

def on_message(client, userdata, message):
    print(message.topic, message.payload.decode())

client.on_connect = on_connect
client.on_message = on_message
client.connect("mqtt.iee305.code-lab.org", 443)
client.loop_forever()
```

Common mistakes:

- **Code from older tutorials.** Many tutorials, and many chatbot answers, use Paho 1.x callbacks such as `on_connect(client, userdata, flags, rc)`. With `VERSION2`, callbacks take the arguments shown above; mixing the two styles fails with `TypeError: on_connect() takes 4 positional arguments but 5 were given`. Leaving out `VERSION2` runs the old style with a `DeprecationWarning`.
- **A fixed client ID.** Do not pass `client_id=...` unless it is unique to you. When two clients use the same ID, the broker disconnects the older one, and both keep knocking each other off.
- **Port and transport mismatch.** Port 443 needs `transport="websockets"`. Plain `connect(..., 8883)` needs the default TCP transport. Both need `tls_set(...)`.
- **No network loop.** Nothing is sent or received unless `loop_forever()` runs, or `loop_start()` runs in the background.
- **Topic typos.** Topics are case-sensitive and have no leading `/`. Wildcards `+` and `#` work only in subscriptions.
- **Passwords in code.** Use `getpass` as above, and do not commit the class password to GitHub.

## Lecture 20: Zigbee telemetry

```text
python subscribe.py
python subscribe.py --topic iee305/l20/zigbee2mqtt/HT-1
```

The output shows receipt time in UTC, the retained-message flag, QoS, the MQTT topic, and the payload. The default subscription `iee305/l20/zigbee2mqtt/#` includes all lecture devices (HT-1 temperature/humidity sensor, MB-1 multi-button, WO-1 wall outlet) and bridge metadata. Your account can subscribe but cannot publish here. A quiet sensor may only report periodically or when its value changes.

The browser client shows the same messages as one card per device. Try WO-1's Toggle button: the broker answers `Not authorized`, because the student account may not send device commands.

During the demonstration, identify the publisher, broker, topic, and subscribers. Compare a single-device topic with the wildcard subscription, then explain whether two students receive the same message and whether the device knows who subscribed.

## Troubleshooting

| Message | What to check |
| --- | --- |
| `Broker refused the login: Not authorized` | Retype the class password from Canvas. |
| `Could not reach ...` | Check your internet connection and the hostname. |
| `TLS certificate check failed` | Check your computer's clock, then run `python -m pip install --upgrade certifi`. |
| `ModuleNotFoundError: No module named 'paho'` | Use the `.venv` Python shown above, from the `students` folder, after the `pip install` step. |
| Connected, but no messages appear | Check the topic spelling. A subscription outside your permissions is accepted but receives nothing. |
