# IEE 305 — MQTT examples for Lectures 19 and 20

One MQTT broker on an Amazon Linux 2023 EC2 host, `mqtt.iee305.code-lab.org`, supports two lectures:

- **L-19, publish and subscribe:** students use the Paho Python library to publish and subscribe under `iee305/l19/`.
- **L-20, Zigbee to MQTT:** Zigbee2MQTT runs beside a SONOFF USB dongle on a Raspberry Pi 3 and publishes telemetry from a temperature/humidity sensor (HT-1), a multi-button (MB-1), and a wall outlet (WO-1); students subscribe under `iee305/l20/` but cannot send device commands.

The same host also serves a **browser client** at `https://mqtt.iee305.code-lab.org/`. It works as the class display for both lectures, and as a second kind of client for students: an MQTT.js client in the browser, using the same broker, password, and topic permissions as the Python scripts.

```text
Zigbee devices --radio--> SONOFF ZBDongle-E --USB--> Raspberry Pi
                                                  Zigbee2MQTT container
                                                   | MQTT over secure WebSockets :443
                                                   v
                    Let's Encrypt <--:80--    EC2: certbot, nginx, Mosquitto
                                                   |  :443 HTTPS: browser page, and WebSockets (nginx -> Mosquitto)
                                                   |  :8883 MQTT/TLS (Mosquitto)
                                                   +--> student Python clients, browsers, and the class display

Instructor browser --> localhost:8080 --SSH tunnel--> Pi frontend on 127.0.0.1:8080
```

## Files and access scheme

| Location | Purpose |
| --- | --- |
| `ec2/compose.yaml`, `mosquitto.conf`, `acl` | Broker, its listeners, topic permissions, nginx, and the certbot renewal service |
| `ec2/nginx.conf`, `ec2/web/` | HTTPS on port 443: the browser client (`index.html`, `app.js`, `style.css`) and the WebSocket proxy to Mosquitto |
| `ec2/setup.sh`, `certbot-deploy.sh`, `password.sh` | Obtain the Let's Encrypt certificate, install it for nginx and Mosquitto, and create/rotate passwords |
| `local/compose.yaml`, `configuration.example.yaml` | Raspberry Pi Zigbee2MQTT service, SONOFF Ember adapter, and MQTT settings |
| `students/` | `subscribe.py`, `publish.py`, `chat.py`, and their [README](students/README.md) |
| `check_access.py` | Live TLS/authentication/authorization check for both lectures, without the dongle |
| `clear_retained.py` | Instructor cleanup of retained messages students leave under `iee305/l19/class/` |

Two accounts keep the example simple:

| MQTT username | Share with | Used by |
| --- | --- | --- |
| `instructor` | Instructor only | Zigbee2MQTT, broadcasts, `check_access.py`, `clear_retained.py` |
| `student` | Enrolled students through Canvas | Every student, for both lectures |

| Topic | `instructor` | `student` |
| --- | --- | --- |
| `iee305/l19/class/#` | publish and subscribe | publish and subscribe |
| `iee305/l19/instructor/#` | publish and subscribe | subscribe only |
| `iee305/l20/#` (Zigbee2MQTT) | publish and subscribe | subscribe only |

Passwords are created at setup; there are no working default credentials. The shared student password keeps internet scanners and drive-by clients out, but it can be forwarded and provides no individual attribution or revocation: within `iee305/l19/class/`, any student can publish to any topic. That is acceptable for a classroom sandbox, and a useful discussion point. Rotate the password at the end of the semester or if it is disclosed. Students do not receive SSH accounts or AWS credentials. If individual accountability becomes necessary, create one MQTT user per student and an ACL `pattern readwrite iee305/l19/class/%u/#` instead.

The host presents a publicly trusted **Let's Encrypt** certificate, so every client verifies it with an ordinary public CA list (`certifi` in Python, Node's built-in list in Zigbee2MQTT, the browser's own list) and no certificate file is distributed. A `certbot` container renews it automatically. Two ports carry MQTT, with the same certificate and accounts:

- **443, HTTPS.** nginx ends TLS and serves the browser client. Connections that ask to upgrade to a WebSocket, on any path, go to Mosquitto's internal WebSockets listener. This is the default for students, browsers, and the Pi, because networks that block 8883 almost never block 443.
- **8883, MQTT over TLS.** Mosquitto's standard native MQTT port, kept for clients that cannot use WebSockets.

Port 80 is used only by certbot for Let's Encrypt's HTTP-01 challenge. The Zigbee2MQTT frontend is bound to the Pi's loopback port 8080; the instructor reaches it through an SSH tunnel.

The browser page is static: nginx sends the same files to anyone, and the page holds no secrets. A visitor sees nothing until they log in with an MQTT username and password, and the broker's ACL governs that login exactly as it governs the Python scripts. The password stays in the page's memory and is never stored.

Images are pinned to Mosquitto `2.1.2-alpine` (password-file and ACL-file plugins), nginx `1.30.6-alpine`, certbot `v5.8.0`, and Zigbee2MQTT `2.14.2`. The page loads MQTT.js `5.16.1` from jsDelivr with a Subresource Integrity hash.

## 1. Prepare the EC2 host

Use an **Amazon Linux 2023** EC2 instance with SSH key authentication. Both x86_64 and ARM64/Graviton hosts work with the images; the Pi and EC2 host do not need matching CPU architectures. AWS provides a Docker package for AL2023; see [AWS's Docker installation instructions](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-docker.html).

The course uses the DNS name `mqtt.iee305.code-lab.org`, an A record pointing at the instance. Associate an **Elastic IP** so the record stays valid, because a normal EC2 public IPv4 address can change after stop/start. Let's Encrypt validates the DNS name, so the A record must point at this instance before running setup. AWS resources and public IPv4 addresses incur charges; shut down or remove them when finished. If you redeploy under another name, substitute it throughout and in the scripts' `BROKER` constants.

The standard AMI login is `ec2-user`. From **Windows PowerShell**, substituting your private-key path:

```powershell
ssh -i 'C:\path\course-ec2.pem' ec2-user@mqtt.iee305.code-lab.org
```

**Prerequisites:** Git, Docker Engine enabled at boot, and the [Docker Compose plugin](https://docs.docker.com/compose/install/linux/), with `ec2-user` in the `docker` group. On AL2023, `sudo dnf install -y git docker` provides Git and Docker Engine; the Compose plugin is installed separately. In the **EC2 SSH terminal**, as **ec2-user**, confirm both work without `sudo`, then clone the repository:

```bash
docker info
docker compose version
cd ~
git clone https://github.com/ptgrogan/iee305-mqtt.git
```

Run the remaining commands as `ec2-user`, using `sudo` only where shown.

In the EC2 security group, allow:

| Direction | Protocol / port | Source | Purpose |
| --- | --- | --- | --- |
| Inbound | TCP 22 (SSH) | Your current public IP `/32` | Administration |
| Inbound | TCP 80 (HTTP) | `0.0.0.0/0` | Let's Encrypt validation; required for issuance and renewal |
| Inbound | TCP 443 (HTTPS and MQTT over WebSockets) | `0.0.0.0/0` | Browser page; students on any network, and the Pi |
| Inbound | TCP 8883 (MQTT over TLS) | `0.0.0.0/0`, or narrower, or closed | Optional native MQTT |
| Outbound | Default outbound access | | Image downloads, package updates, Let's Encrypt, and DNS |

Let's Encrypt validates from several unpublished locations, so port 80 cannot be restricted to known addresses; certbot only listens on it for the few seconds of a renewal. TLS and the MQTT password and ACL enforce access on 443 and 8883. Do not add inbound 1883, 8080, or 9001. See [AWS security-group examples](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html).

In the **EC2 SSH terminal**, pass the DNS name without a scheme or port, and optionally an email address for your Let's Encrypt account:

```bash
cd ~/iee305-mqtt/ec2
bash setup.sh mqtt.iee305.code-lab.org
# Prompts twice each for the instructor and student passwords. Use different, strong passwords.
docker compose up -d
docker compose ps
docker compose logs --tail=60 mosquitto web
```

The setup script runs certbot once in standalone mode to obtain the certificate, then runs `certbot-deploy.sh` to copy the key and chain into the `tls` volume, readable by nginx and by the container's Mosquitto group (1883). Certbot's account and keys stay in the `letsencrypt` volume, which is never mounted into the broker. Passwords are stored as hashes in `runtime/auth/passwd`. If the two entries of a password do not match, setup asks again. Setup is safe to re-run: it keeps an unexpired certificate, avoiding Let's Encrypt rate limits, keeps any password already set, and prompts only for a missing one. Change a password at any time with `password.sh`; see Operations below.

After `docker compose up -d`, the `certbot` service checks twice a day and renews the certificate once it enters its renewal window, well before it expires (Let's Encrypt certificates last 90 days or less). Its deploy hook installs the renewed files; within an hour the Mosquitto and nginx healthchecks notice the new certificate and reload it (`SIGHUP` and `nginx -s reload`), without disconnecting clients.

Never commit or distribute anything from `runtime/`, the Docker volumes, the local `.env`, or the instructor password.

## 2. Prepare the Raspberry Pi and USB dongle

Use your **Raspberry Pi 3 with its existing Raspberry Pi OS (64-bit)**, a suitable power supply, and a reliable network connection. The Compose service selects `linux/arm64`, which matches this OS; no architecture change or OS reinstallation is needed. Raspberry Pi documents the Pi 3's ARM64 support in its [64-bit OS announcement](https://www.raspberrypi.com/news/raspberry-pi-os-64-bit/). Enable SSH and configure the network if needed. The examples below use hostname `iee305-pi.local`; replace it with your Pi's hostname or LAN IP, and replace `YOUR_PI_USER` with your chosen username.

For this small lecture example, the Pi hosts Zigbee2MQTT while EC2 hosts the broker and student connections. Keep other workloads light on the Pi and allow time for the first image download. If provisioning a fresh SD card later, Raspberry Pi OS Lite (64-bit) avoids running an unnecessary desktop.

From **Windows PowerShell**, connect to the Pi:

```powershell
ssh YOUR_PI_USER@iee305-pi.local
```

On the **Pi**, confirm that `dpkg --print-architecture` reports `arm64`, then install Docker Engine and the Compose plugin using [Docker's Debian instructions](https://docs.docker.com/engine/install/debian/) for the Debian release underlying your Pi OS. Use the Debian `arm64` packages for this 64-bit OS. Complete Docker's documented group setup so your login user can run Docker, then reconnect your SSH session.

On the **Pi**:

```bash
dpkg --print-architecture
sudo apt update
sudo apt install git usbutils python3-venv
sudo systemctl enable --now docker
docker info
docker compose version
```

Attach the antenna, then plug the ZBDongle-E into the Pi, preferably through a short USB extension away from USB 3 equipment and Wi-Fi antennas. Verify it on the **Pi**:

```bash
lsusb
ls -l /dev/serial/by-id/
```

Copy the SONOFF `/dev/serial/by-id/...` path into `local/.env`. This stable path is mapped to `/dev/ttyUSB0` inside the container, regardless of the host's numbered device name. The service uses Docker's explicit device mapping; no privileged container is required. The Pi connects outbound to the broker on TCP 443.

The dongle must run **Zigbee coordinator/NCP firmware** supported by Zigbee2MQTT's Ember driver, with software flow control at 115200 baud. Router, Thread, and multiprotocol firmware will not work for this configuration. Check the firmware before class using [SONOFF's guide](https://dongle.sonoff.tech/guide/zbdongle-e/connecting_to_zigbee2mqtt/) and the [Zigbee2MQTT Ember documentation](https://www.zigbee2mqtt.io/guide/adapters/emberznet.html). If your installed coordinator firmware uses another baud rate, change `serial.baudrate` to match. Do not let another Zigbee service open the adapter concurrently.

## 3. Start Zigbee2MQTT on the Pi

The folder remains named `local/` to distinguish the Pi service from the EC2 broker. In the **Pi SSH terminal**, clone the repository over HTTPS and prepare the persistent configuration on the Pi's Linux filesystem:

```bash
cd ~
git clone https://github.com/ptgrogan/iee305-mqtt.git
cd ~/iee305-mqtt/local
bash prepare.sh
nano .env
```

`MQTT_HOST` defaults to `mqtt.iee305.code-lab.org`. Set `MQTT_PASSWORD` to the **instructor** MQTT password, and `ZIGBEE_DEVICE` to the actual Linux device path. Quoting the password with single quotes in `.env` preserves `$` and `#`; the example asks you to avoid single quotes in this password. Compose passes the connection settings as environment variables, which override the YAML values; the server is `wss://MQTT_HOST:443`. To use native MQTT instead, change that line in `compose.yaml` to `mqtts://...:8883`.

On the **Pi**, from `~/iee305-mqtt/local`:

```bash
chmod 600 .env
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose logs -f --tail=60 zigbee2mqtt
```

Use `--quiet` when checking Compose configuration: normal `docker compose config` output includes the resolved password. Once started, the service restarts automatically after a Pi reboot because Docker is enabled at boot and the container uses `restart: unless-stopped`.

Open a separate **Windows PowerShell** terminal for an SSH tunnel:

```powershell
ssh -N -L 8080:127.0.0.1:8080 YOUR_PI_USER@iee305-pi.local
```

Keep that terminal open, then open [the frontend](http://localhost:8080) in your Windows browser. The tunnel connects your computer's port 8080 to the Pi's loopback port 8080; the Pi's LAN address on port 8080 is not the browser URL for this setup.

On a new network, Zigbee2MQTT creates and saves random Zigbee keys and PAN IDs in `local/data/`. Preserve this folder between restarts; replacing it can require pairing devices again. The template selects Zigbee channel 20; check local Wi-Fi interference before pairing. Pairing starts closed. In the frontend, permit joining for a short interval, put a device into pairing mode, and close joining when done. Rename each device to its label, `HT-1`, `MB-1`, and `WO-1`, for readable topics:

```text
iee305/l20/zigbee2mqtt/HT-1
iee305/l20/zigbee2mqtt/MB-1
iee305/l20/zigbee2mqtt/WO-1
```

The browser client builds its device cards from the retained `bridge/devices` message, so it needs no change when devices are added or renamed.

## 4. Give students the repository

Share three things through Canvas: the repository URL, the browser client URL `https://mqtt.iee305.code-lab.org/`, and the class password for username `student`. Students need Git and Python 3.10+ for the scripts, or only a browser for the page; they need no certificate file, dongle, Docker, or AWS account. [students/README.md](students/README.md) has their setup commands, the L-19 and L-20 instructions, and a troubleshooting table. The same password works for both lectures and both clients.

The scripts connect over secure WebSockets on port 443 and verify the certificate with `certifi`, the Python package of public CAs. Using `certifi` explicitly avoids a common macOS problem, where Python from python.org has no CA list until its "Install Certificates" step is run. Each client gets a distinct broker-assigned ID; students should not all use the same fixed client ID, because the broker disconnects an existing session when another client connects with the same ID.

### The browser client and class display

Open `https://mqtt.iee305.code-lab.org/` and log in. Username `student` is filled in; the instructor can type `instructor` instead. The page has three collapsible panels:

- **Lecture 19:** a live table of messages on a topic filter (default `iee305/l19/#`), with the same columns as `subscribe.py`. It also has a publish form with QoS and retain options, which shows the broker's response as `publish.py` does: `Success`, `No matching subscribers`, or `Not authorized`.
- **Lecture 20:** one card per Zigbee2MQTT device: temperature and humidity for HT-1, the last button action for MB-1, and state and power for WO-1. Each card also lists battery, link quality, and last seen, and is labelled when a value is the broker's retained copy. Outlet cards have On/Off/Toggle buttons that publish to `<device>/set`; they work for `instructor` and return `Not authorized` for `student`.
- **Chat:** joins the same rooms as `chat.py`, with the same JSON format and Last Will, so browser and Python users talk to each other.

The page opens with Lecture 19 expanded and Lecture 20 collapsed. Click a panel's title to collapse or expand it. While both lectures are open they sit side by side; while one is collapsed the other takes the full width. For L-20, share `https://mqtt.iee305.code-lab.org/?lecture=20` on Canvas, which opens with only Lecture 20 expanded; `?lecture=19` gives the default view. Chat counts as part of L-19.

For the projector, press **Class display**, or open `https://mqtt.iee305.code-lab.org/?display`, which combines with the lecture link, as in `?display&lecture=20`. Display mode enlarges the type and hides the forms, leaving the message feed and device cards. On a projected screen, log in as `student`. Switch out of display mode to use the outlet buttons as `instructor`.

The page itself is a teaching example. `ec2/web/app.js` is a short, commented MQTT.js client: connect, subscribe, publish, and handle messages, the same steps as the Python template in a different language and runtime. To try changes before deploying, open `ec2/web/index.html` directly from disk. A page opened as a local file connects to the class broker, and `?broker=wss://HOST/mqtt` points it at another one.

## 5. Lecture 19: publish and subscribe

Students publish under `iee305/l19/class/`, conventionally `iee305/l19/class/ASURITE/...`, and can read everything under `iee305/l19/`. Only the instructor can publish under `iee305/l19/instructor/`. Suggested sequence:

1. Project the class display, `?display`. Everyone runs `subscribe.py --topic "iee305/l19/#"`. Publish a broadcast with `publish.py iee305/l19/instructor/announce "Welcome to L-19" --username instructor`; it appears on every terminal and on the projector at once.
2. Students publish to their own topic with `publish.py`, then subscribe to `iee305/l19/class/+/hello` to see the single-level wildcard collect everyone's messages.
3. **Retained messages:** publish with `--retain`, then start a new subscriber; it receives the saved value immediately with `retain=True`. Note that `No matching subscribers` is a successful broker response, not an error.
4. **QoS:** compare `--qos 0`, `1`, and `2`; with QoS 0 there is no broker acknowledgment.
5. **Authorization:** a student publish to `iee305/l19/instructor/...` or `iee305/l20/...` returns `Not authorized`. The login succeeded; authentication and authorization are different checks.
6. **Event-driven clients:** run `chat.py` in pairs. It uses `loop_start()` so the main thread can read the keyboard, JSON payloads, and a **Last Will**: close a chat window abruptly and the broker announces `(lost connection)`.
7. **Another kind of client:** students open the browser client, publish from it, and join a chat room alongside `chat.py` users. Closing the browser tab triggers the Last Will just as closing a terminal does. Compare `ec2/web/app.js` with `subscribe.py`: different language and library, the same broker, credentials, topics, and callbacks.
8. Students write their own client from the template in the student README.

After class, clear retained messages students left behind. From the repository root, in a Python environment with `students/requirements.txt` installed:

```bash
.venv/bin/python clear_retained.py --dry-run
.venv/bin/python clear_retained.py
```

## 6. Lecture 20: Zigbee telemetry

`subscribe.py` with no options subscribes to `iee305/l20/zigbee2mqtt/#`: device messages and bridge metadata. Narrow it with `--topic iee305/l20/zigbee2mqtt/HT-1`. The class display shows the same subscription as device cards.

The output contains the **receipt time** in UTC, `retain`, QoS, topic, and JSON payload. A receipt timestamp is not the sensor's sampling time. The template also enables a device `last_seen` field. Some devices send on change or periodically; a quiet sensor is not necessarily disconnected. A retained message, when present, represents the broker's saved last value, not necessarily a fresh observation.

Suggested live sequence:

1. Project the class display, `?display&lecture=20`, and run two subscribers, then press MB-1 or breathe on HT-1. Trace device → coordinator → Zigbee2MQTT → EC2 broker → both subscribers and the display.
2. Compare a wildcard subscription with a single device topic. Inspect JSON fields; their names depend on the device. Expand "All messages" on the display to see the raw messages behind the cards.
3. Discuss publishers, topics, subscriptions, and how the broker distributes a message without the sensor knowing subscribers' addresses.
4. Show that student credentials authenticate successfully while publishing to `iee305/l20/...` is denied. Students can press WO-1's Toggle in their own browser and see `Not authorized`.
5. Log in as `instructor` and toggle WO-1. The command goes to `iee305/l20/zigbee2mqtt/WO-1/set`; Zigbee2MQTT, subscribed to it, switches the outlet and publishes the new state, which every subscriber sees. Students remain observers.

## 7. Rehearse access

Before each lecture, from the repository root on the classroom network (the Pi or any computer with a current checkout), with the broker running:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r students/requirements.txt
.venv/bin/python check_access.py
```

It prompts for both passwords and checks that the browser page loads over HTTPS. Over WebSockets on 443, through nginx on both the `/mqtt` and `/` paths, and over MQTT/TLS on 8883, it checks verified TLS, rejection of anonymous and bad-password logins, and that:

- a student receives the instructor's L-20 messages but cannot publish to L-20;
- two students can exchange messages under `iee305/l19/class/`;
- a student receives instructor broadcasts but cannot publish under `iee305/l19/instructor/`.

Test messages are non-retained and use unique `.../access-check/...` topics, outside the Zigbee command path. A successful check verifies the broker without a USB dongle; still rehearse actual sensor reports separately. If 8883 fails but 443 passes, the network blocks 8883; the student scripts are unaffected.

## Operations and troubleshooting

- **Update source:** commit and push source changes from your development computer, then `cd ~/iee305-mqtt` and `git pull --ff-only` on EC2 and the Pi. Run `docker compose up -d` from `ec2/` or `local/` as appropriate; after changing `mosquitto.conf` or `acl`, run `docker compose restart mosquitto`, and after changing `nginx.conf`, `docker compose restart web`. Changes under `ec2/web/` take effect on the next page load. Git leaves ignored credentials and runtime state on each host. Keep `.env`, `ec2/runtime/`, and `local/data/` out of commits, and preserve them between updates.
- **Rotate class access:** on EC2, `bash password.sh student`. If the broker is running, the script signals it to reload the password file, so new logins need the new password immediately; clients already connected stay connected. To disconnect them too, follow with `docker compose restart mosquitto`. Update Canvas. Rotate `instructor` similarly, update `local/.env`, then run `docker compose up -d --force-recreate zigbee2mqtt` on the Pi.
- **Certificate status:** on EC2, `docker compose exec certbot certbot certificates` shows the expiry date; `docker compose exec certbot certbot renew --dry-run` tests renewal against Let's Encrypt's staging service. `docker compose ps` should show Mosquitto as `healthy`. Renewal needs inbound port 80 and a correct A record.
- **TLS failure:** the hostname must be exactly `mqtt.iee305.code-lab.org`; check the client's clock and run `pip install --upgrade certifi`. Keep certificate verification enabled.
- **Timeout:** check the A record, the security-group rules for 443/8883, and `docker compose logs mosquitto web`. If only 8883 fails, the client's network is blocking it; use 443. Mosquitto's log shows nginx's container address for every WebSocket client; nginx's access log records the client addresses.
- **Browser page:** if Connect does nothing, MQTT.js probably did not load from jsDelivr; check the browser's developer console. Students should hard-refresh after a page update. `Could not reach ...` on the page is the same check as for the scripts.
- **USB missing:** on the Pi, check power, the USB connection, `lsusb`, and the `/dev/serial/by-id/` path in `.env`. After unplugging and reconnecting the dongle, run `docker compose up -d --force-recreate zigbee2mqtt` on the Pi.
- **Ember startup error:** check coordinator firmware, baud rate, software flow control, and whether another process owns the adapter.
- **Computer port 8080 busy:** leave the Pi Compose file as supplied, use `ssh -N -L 8081:127.0.0.1:8080 YOUR_PI_USER@iee305-pi.local`, then browse to `http://localhost:8081`. If port 8080 is occupied on the Pi itself, change the Compose mapping to `127.0.0.1:8081:8080` and point the tunnel's destination at port 8081.
- **Stop the demonstration:** run `docker compose down` in each Compose directory. The broker, certificate, and local Zigbee state are preserved in volumes and `local/data/`. Stop/terminate EC2 and release unneeded paid resources separately.

## References

- [AWS Docker installation on Amazon Linux 2023](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-docker.html)
- [Docker Compose plugin installation](https://docs.docker.com/compose/install/linux/)
- [Let's Encrypt challenge types](https://letsencrypt.org/docs/challenge-types/), [certbot user guide](https://eff-certbot.readthedocs.io/en/stable/using.html)
- [Mosquitto configuration](https://mosquitto.org/man/mosquitto-conf-5.html), [password-file plugin](https://mosquitto.org/documentation/plugins/password-file/), [ACL-file plugin](https://mosquitto.org/documentation/plugins/acl-file/)
- [Raspberry Pi setup and OS installation](https://www.raspberrypi.com/documentation/computers/getting-started.html)
- [Docker Engine for Debian / Raspberry Pi OS 64-bit](https://docs.docker.com/engine/install/debian/)
- [Zigbee2MQTT Docker/Compose installation](https://www.zigbee2mqtt.io/guide/installation/02_docker.html)
- [Zigbee2MQTT MQTT settings](https://www.zigbee2mqtt.io/guide/configuration/mqtt.html), [topics and messages](https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html)
- [Paho MQTT Python client documentation](https://eclipse.dev/paho/clients/python/docs/)
- [MQTT.js](https://github.com/mqttjs/MQTT.js), [nginx WebSocket proxying](https://nginx.org/en/docs/http/websocket.html)
