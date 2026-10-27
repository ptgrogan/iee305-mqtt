# IEE 305 — MQTT examples for Lectures 19 and 20

One MQTT broker on an Amazon Linux 2023 EC2 host, `mqtt.iee305.code-lab.org`, supports two lectures:

- **L-19, publish and subscribe:** students use the Paho Python library to publish and subscribe under `iee305/l19/`.
- **L-20, Zigbee to MQTT:** Zigbee2MQTT runs beside a SONOFF USB dongle on a Raspberry Pi 3 and publishes sensor telemetry; students subscribe under `iee305/l20/` but cannot send device commands.

```text
Zigbee sensor --radio--> SONOFF ZBDongle-E --USB--> Raspberry Pi
                                                 Zigbee2MQTT container
                                                  | MQTT over secure WebSockets :443
                                                  v
                    Let's Encrypt <--:80--   EC2: certbot + Mosquitto
                                                  |  :443 (WebSockets), :8883 (MQTT/TLS)
                                                  +--> student Python publishers and subscribers

Instructor browser --> localhost:8080 --SSH tunnel--> Pi frontend on 127.0.0.1:8080
```

## Files and access scheme

| Location | Purpose |
| --- | --- |
| `ec2/compose.yaml`, `mosquitto.conf`, `acl` | Broker, its two TLS listeners, topic permissions, and the certbot renewal service |
| `ec2/setup.sh`, `certbot-deploy.sh`, `password.sh` | Obtain the Let's Encrypt certificate, install it for Mosquitto, and create/rotate passwords |
| `ec2/install-compose.sh` | Install the Compose CLI plugin on Amazon Linux 2023 if it is missing |
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

The broker presents a publicly trusted **Let's Encrypt** certificate, so every client verifies it with an ordinary public CA list (`certifi` in Python, Node's built-in list in Zigbee2MQTT) and no certificate file is distributed. A `certbot` container renews it automatically. Mosquitto listens on two ports with the same certificate and accounts:

- **443, MQTT over secure WebSockets.** The default for students and the Pi, because networks that block 8883 almost never block 443.
- **8883, MQTT over TLS.** The standard native MQTT port, kept for clients that cannot use WebSockets.

Port 80 is used only by certbot for Let's Encrypt's HTTP-01 challenge. The Zigbee2MQTT frontend is bound to the Pi's loopback port 8080; the instructor reaches it through an SSH tunnel.

Images are pinned to Mosquitto `2.1.2-alpine` (password-file and ACL-file plugins), certbot `v5.8.0`, and Zigbee2MQTT `2.14.2`.

## 1. Prepare the EC2 host

Use an **Amazon Linux 2023** EC2 instance with SSH key authentication. Both x86_64 and ARM64/Graviton hosts work with the images; the Pi and EC2 host do not need matching CPU architectures. AWS provides a Docker package for AL2023; see [AWS's Docker installation instructions](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-docker.html).

The course uses the DNS name `mqtt.iee305.code-lab.org`, an A record pointing at the instance. Associate an **Elastic IP** so the record stays valid, because a normal EC2 public IPv4 address can change after stop/start. Let's Encrypt validates the DNS name, so the A record must point at this instance before running setup. AWS resources and public IPv4 addresses incur charges; shut down or remove them when finished. If you redeploy under another name, substitute it throughout and in the scripts' `BROKER` constants.

The standard AMI login is `ec2-user`. From **Windows PowerShell**, substituting your private-key path:

```powershell
ssh -i 'C:\path\course-ec2.pem' ec2-user@mqtt.iee305.code-lab.org
```

In the **EC2 SSH terminal**, install Git and Docker, enable Docker at boot, and grant the login user Docker access:

```bash
sudo dnf install -y git docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
exit
```

Reconnect with SSH so the new group membership takes effect. Then, as **ec2-user**:

```bash
docker info
cd ~
git clone https://github.com/ptgrogan/iee305-mqtt.git
cd ~/iee305-mqtt/ec2
# The standard AL2023 AMI supplies curl. If missing: sudo dnf install -y curl-minimal
bash install-compose.sh
docker compose version
```

The helper follows [Docker's manual Compose-plugin installation method](https://docs.docker.com/compose/install/linux/). It installs Compose `v5.6.0` for the current user after checking the architecture-specific SHA-256 digest, or preserves an existing Compose installation. Run the remaining commands as `ec2-user`, using `sudo` only where shown.

In the EC2 security group, allow:

| Direction | Protocol / port | Source | Purpose |
| --- | --- | --- | --- |
| Inbound | TCP 22 (SSH) | Your current public IP `/32` | Administration |
| Inbound | TCP 80 (HTTP) | `0.0.0.0/0` | Let's Encrypt validation; required for issuance and renewal |
| Inbound | TCP 443 (MQTT over WebSockets) | `0.0.0.0/0` | Students on any network, and the Pi |
| Inbound | TCP 8883 (MQTT over TLS) | `0.0.0.0/0`, or narrower, or closed | Optional native MQTT |
| Outbound | Default outbound access | | Image downloads, package updates, Let's Encrypt, and DNS |

Let's Encrypt validates from several unpublished locations, so port 80 cannot be restricted to known addresses; certbot only listens on it for the few seconds of a renewal. TLS and the MQTT password and ACL enforce access on 443 and 8883. Do not add inbound 1883, 8080, or 9001. See [AWS security-group examples](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html).

In the **EC2 SSH terminal**, pass the DNS name without a scheme or port, and optionally an email address for your Let's Encrypt account:

```bash
cd ~/iee305-mqtt/ec2
bash setup.sh mqtt.iee305.code-lab.org
# On first setup, prompts twice for each password. Use different, strong passwords.
docker compose up -d
docker compose ps
docker compose logs --tail=60 mosquitto
```

The setup script runs certbot once in standalone mode to obtain the certificate, then runs `certbot-deploy.sh` to copy the key and chain into the `tls` volume, readable by the container's Mosquitto group (1883). Certbot's account and keys stay in the `letsencrypt` volume, which is never mounted into the broker. Passwords are stored as hashes in `runtime/auth/passwd`. Setup is safe to re-run: it keeps an unexpired certificate (avoiding Let's Encrypt rate limits) and existing passwords. If it stops during the password prompts, finish with `bash password.sh instructor` and `bash password.sh student`.

After `docker compose up -d`, the `certbot` service checks twice a day and renews the certificate once it enters its renewal window, well before it expires (Let's Encrypt certificates last 90 days or less). Its deploy hook installs the renewed files; the Mosquitto healthcheck notices the new certificate within an hour and sends Mosquitto `SIGHUP`, which reloads the certificate without disconnecting clients.

Never commit or distribute anything from `runtime/`, the Docker volumes, the local `.env`, or the instructor password.

### Migrating from the original teaching CA

A broker set up with the earlier private "IEE305 Lecture 20 Teaching CA" keeps its passwords: because `runtime/auth/passwd` already exists, setup does not prompt for them. To choose new ones, run `bash password.sh student` (or `instructor`) afterwards. Open ports 80 and 443 in the security group first. Then, on **EC2**:

```bash
cd ~/iee305-mqtt && git pull --ff-only && cd ec2
docker compose down
bash setup.sh mqtt.iee305.code-lab.org
docker compose up -d
rm -rf runtime/private runtime/certs runtime/broker-host.txt  # retire the teaching CA
```

Then update the Pi as described at the end of section 3. Any `ca.crt` copies handed out earlier are no longer needed.

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

On a new network, Zigbee2MQTT creates and saves random Zigbee keys and PAN IDs in `local/data/`. Preserve this folder between restarts; replacing it can require pairing devices again. The template selects Zigbee channel 20; check local Wi-Fi interference before pairing. Pairing starts closed. In the frontend, permit joining for a short interval, put a sensor into pairing mode, and close joining when done. Rename a sensor to `lecture_sensor` for a readable topic:

```text
iee305/l20/zigbee2mqtt/lecture_sensor
```

**Updating a Pi prepared for the teaching CA:** its `data/configuration.yaml` still names the old CA file, which is no longer mounted. On the **Pi**:

```bash
cd ~/iee305-mqtt && git pull --ff-only && cd local
sed -i '/^  ca: \/app\/ca.crt$/d' data/configuration.yaml
docker compose up -d --force-recreate
rm -rf certs
```

## 4. Give students the repository

Share two things through Canvas: the repository URL and the class password for username `student`. Students need Git and Python 3.10+; they need no certificate file, dongle, Docker, or AWS account. [students/README.md](students/README.md) has their setup commands, the L-19 and L-20 instructions, and a troubleshooting table. The same clone and password work for both lectures.

The scripts connect over secure WebSockets on port 443 and verify the certificate with `certifi`, the Python package of public CAs. Using `certifi` explicitly avoids a common macOS problem, where Python from python.org has no CA list until its "Install Certificates" step is run. Each client gets a distinct broker-assigned ID; students should not all use the same fixed client ID, because the broker disconnects an existing session when another client connects with the same ID.

## 5. Lecture 19: publish and subscribe

Students publish under `iee305/l19/class/`, conventionally `iee305/l19/class/ASURITE/...`, and can read everything under `iee305/l19/`. Only the instructor can publish under `iee305/l19/instructor/`. Suggested sequence:

1. Everyone runs `subscribe.py --topic "iee305/l19/#"`. Publish a broadcast with `publish.py iee305/l19/instructor/announce "Welcome to L-19" --username instructor`.
2. Students publish to their own topic with `publish.py`, then subscribe to `iee305/l19/class/+/hello` to see the single-level wildcard collect everyone's messages.
3. **Retained messages:** publish with `--retain`, then start a new subscriber; it receives the saved value immediately with `retain=True`. Note that `No matching subscribers` is a successful broker response, not an error.
4. **QoS:** compare `--qos 0`, `1`, and `2`; with QoS 0 there is no broker acknowledgment.
5. **Authorization:** a student publish to `iee305/l19/instructor/...` or `iee305/l20/...` returns `Not authorized`. The login succeeded; authentication and authorization are different checks.
6. **Event-driven clients:** run `chat.py` in pairs. It uses `loop_start()` so the main thread can read the keyboard, JSON payloads, and a **Last Will**: close a chat window abruptly and the broker announces `(lost connection)`.
7. Students write their own client from the template in the student README.

After class, clear retained messages students left behind. From the repository root, in a Python environment with `students/requirements.txt` installed:

```bash
.venv/bin/python clear_retained.py --dry-run
.venv/bin/python clear_retained.py
```

## 6. Lecture 20: Zigbee telemetry

`subscribe.py` with no options subscribes to `iee305/l20/zigbee2mqtt/#`: device messages and bridge metadata. Narrow it with `--topic iee305/l20/zigbee2mqtt/lecture_sensor`.

The output contains the **receipt time** in UTC, `retain`, QoS, topic, and JSON payload. A receipt timestamp is not the sensor's sampling time. The template also enables a device `last_seen` field. Some devices send on change or periodically; a quiet sensor is not necessarily disconnected. A retained message, when present, represents the broker's saved last value, not necessarily a fresh observation.

Suggested live sequence:

1. Run two subscribers, then trigger a sensor. Trace device → coordinator → Zigbee2MQTT → EC2 broker → both subscribers.
2. Compare a wildcard subscription with a single device topic. Inspect JSON fields; their names depend on the device.
3. Discuss publishers, topics, subscriptions, and how the broker distributes a message without the sensor knowing subscribers' addresses.
4. Show that student credentials authenticate successfully while publishing to `iee305/l20/...` is denied.
5. If you have a controllable device, demonstrate a command from the instructor frontend. Zigbee2MQTT subscribes for commands and publishes state. Students remain observers.

## 7. Rehearse access

Before each lecture, from the repository root on the classroom network (the Pi or any computer with a current checkout), with the broker running:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r students/requirements.txt
.venv/bin/python check_access.py
```

It prompts for both passwords. Over WebSockets on 443 and MQTT/TLS on 8883 it checks verified TLS, rejection of anonymous and bad-password logins, and that:

- a student receives the instructor's L-20 messages but cannot publish to L-20;
- two students can exchange messages under `iee305/l19/class/`;
- a student receives instructor broadcasts but cannot publish under `iee305/l19/instructor/`.

Test messages are non-retained and use unique `.../access-check/...` topics, outside the Zigbee command path. A successful check verifies the broker without a USB dongle; still rehearse actual sensor reports separately. If 8883 fails but 443 passes, the network blocks 8883; the student scripts are unaffected.

## Operations and troubleshooting

- **Update source:** commit and push source changes from your development computer, then `cd ~/iee305-mqtt` and `git pull --ff-only` on EC2 and the Pi. Run `docker compose up -d` from `ec2/` or `local/` as appropriate; after changing `mosquitto.conf` or `acl`, run `docker compose restart mosquitto`. Git leaves ignored credentials and runtime state on each host. Keep `.env`, `ec2/runtime/`, and `local/data/` out of commits, and preserve them between updates.
- **Rotate class access:** on EC2, `bash password.sh student`. If the broker is running, the script signals it to reload the password file, so new logins need the new password immediately; clients already connected stay connected. To disconnect them too, follow with `docker compose restart mosquitto`. Update Canvas. Rotate `instructor` similarly, update `local/.env`, then run `docker compose up -d --force-recreate zigbee2mqtt` on the Pi.
- **Certificate status:** on EC2, `docker compose exec certbot certbot certificates` shows the expiry date; `docker compose exec certbot certbot renew --dry-run` tests renewal against Let's Encrypt's staging service. `docker compose ps` should show Mosquitto as `healthy`. Renewal needs inbound port 80 and a correct A record.
- **TLS failure:** the hostname must be exactly `mqtt.iee305.code-lab.org`; check the client's clock and run `pip install --upgrade certifi`. Keep certificate verification enabled.
- **Timeout:** check the A record, the security-group rules for 443/8883, and `docker compose logs mosquitto`. If only 8883 fails, the client's network is blocking it; use 443.
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
