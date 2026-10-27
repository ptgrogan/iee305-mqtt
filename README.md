# IEE 305 — Lecture 20: Zigbee to MQTT

Run Zigbee2MQTT beside the USB dongle on a Raspberry Pi 3 running Raspberry Pi OS (64-bit). Run the MQTT broker on an Amazon Linux 2023 EC2 host. Students subscribe to the same stream independently; the broker distributes each published message to every matching subscriber.

```text
Zigbee sensor --radio--> SONOFF ZBDongle-E --USB--> Raspberry Pi
                                                 Zigbee2MQTT container
                                                  | MQTT over TLS :8883
                                                  v
                                              EC2 Mosquitto
                                                  |
                                                  +--> student Python subscribers

Instructor browser --> localhost:8080 --SSH tunnel--> Pi frontend on 127.0.0.1:8080
```

## Files and access scheme

| Location | Purpose |
| --- | --- |
| `local/compose.yaml` | Raspberry Pi Zigbee2MQTT service and explicit USB device mapping |
| `local/configuration.example.yaml` | SONOFF Ember adapter, Zigbee network, MQTT, and frontend settings |
| `ec2/compose.yaml`, `mosquitto.conf`, `acl` | Persistent broker, TLS listener, and topic permissions |
| `ec2/install-compose.sh` | Install the Compose CLI plugin on Amazon Linux 2023 if it is missing |
| `ec2/setup.sh`, `password.sh` | Generate certificates and interactively create/rotate passwords |
| `students/subscribe.py`, `requirements.txt` | Small Python subscriber for class |
| `check_access.py` | Live TLS/authentication/authorization check, without requiring the dongle |

Two accounts keep the example simple:

| MQTT username | Share with | Permissions |
| --- | --- | --- |
| `instructor` | Instructor only; used by Zigbee2MQTT | Publish and subscribe under `iee305/l20/#` |
| `student` | Enrolled students through Canvas | Subscribe under `iee305/l20/#`; no publishing |

Passwords are created at setup; there are no working default credentials. The shared student password can be forwarded, and it provides no individual attribution or revocation. Rotate it after the demonstration or if it is disclosed. Students do not receive SSH accounts or AWS credentials. If individual revocation becomes necessary, create separate MQTT users and matching ACL entries instead.

All MQTT clients verify the server certificate using the supplied teaching CA. This is ordinary TLS plus username/password authentication; client certificates are not required. Only TCP 8883 is exposed by the broker Compose file. The frontend is bound to the Pi's loopback port 8080; the instructor accesses it through an SSH tunnel.

Images are pinned to Zigbee2MQTT `2.14.2` and Mosquitto `2.1.2-alpine`. The latter uses the Mosquitto 2.1 password-file and ACL-file plugins.

## 1. Prepare the EC2 host

Use an **Amazon Linux 2023** EC2 instance with a public endpoint and SSH key authentication. Both x86_64 and ARM64/Graviton hosts work with the broker image; the Pi and EC2 host do not need matching CPU architectures. The broker runs in a container, so Amazon Linux is a suitable host for this example. AWS provides a Docker package for AL2023; see [AWS's Docker installation instructions](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-docker.html).

The standard AMI login is `ec2-user`. Source files are installed directly from [the GitHub repository](https://github.com/ptgrogan/iee305-mqtt) using Git over HTTPS. From **Windows PowerShell**, connect to EC2, substituting your private-key path and EC2 public hostname:

```powershell
ssh -i 'C:\path\course-ec2.pem' ec2-user@ec2-REPLACE.compute.amazonaws.com
```

In the **EC2 SSH terminal**, install Git, Docker, and OpenSSL, enable Docker at boot, and grant the login user Docker access:

```bash
sudo dnf install -y git docker openssl ca-certificates
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
openssl version
```

The helper follows [Docker's manual Compose-plugin installation method](https://docs.docker.com/compose/install/linux/). It installs Compose `v5.6.0` for the current user after checking the architecture-specific SHA-256 digest, or preserves an existing Compose installation. A manual installation is updated separately from `dnf` packages. Run the remaining example commands as `ec2-user`, using `sudo` only where shown, so this user-installed plugin and file ownership stay consistent.

In the EC2 security group, allow:

| Direction | Protocol / port | Source |
| --- | --- | --- |
| Inbound | TCP 22 (SSH) | Your current public IP `/32` |
| Inbound | TCP 8883 (MQTT over TLS) | Verified classroom/campus public egress CIDRs, the Pi's public egress IP, and the instructor's public IP |
| Outbound | Default outbound access | Image downloads, package updates, and DNS |

If students connect from changing off-campus networks, you may temporarily allow `0.0.0.0/0` on **8883 only**; TLS and the MQTT password/ACL still enforce application access. A campus CIDR alone does not identify enrolled students. Do not add inbound 1883, 8080, or 9001. Use the EC2 security group to control network access. See [AWS security-group examples](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html).

Use a stable endpoint when possible. An Elastic IP or a stable DNS name avoids endpoint changes between rehearsals. A normal EC2 public IPv4 address and its associated hostname can change after stop/start; a changed endpoint needs a matching certificate and updated client settings. AWS resources and public IPv4 addresses incur charges; shut down or remove them when finished.

In an **EC2 SSH terminal**, replace the hostname below with your instance's public DNS name (or public IPv4 address), without a scheme or port:

```bash
cd ~/iee305-mqtt/ec2
bash setup.sh ec2-REPLACE.compute.amazonaws.com
# Prompts twice for each password. Use different, strong passwords.
docker compose config --quiet
docker compose up -d
docker compose logs --tail=60 mosquitto
```

The setup script creates a 365-day CA and a 90-day server certificate with a DNS or IP subject alternative name matching the argument. Keep `runtime/private/ca.key` private; it is not mounted into the broker. `runtime/certs/server.key` is mounted read-only and readable by the container's Mosquitto group (1883). Run this setup from the EC2 Linux filesystem, where Unix permissions work normally.

If setup stops during the password prompts, the certificates remain in `runtime/`. Finish with `bash password.sh instructor` and `bash password.sh student`, then start Compose. The setup script refuses to overwrite an existing `runtime/` directory.

Copy **only** `ec2/runtime/certs/ca.crt` to the Raspberry Pi and into the student handout. It is a public certificate. Never distribute `runtime/`, private keys, password hashes, the local `.env`, or the instructor password. Distribute the CA through the course's trusted channel; students should not fetch a replacement from an unverified broker connection.

## 2. Prepare the Raspberry Pi and USB dongle

Use your **Raspberry Pi 3 with its existing Raspberry Pi OS (64-bit)**, a suitable power supply, and a reliable network connection. The Compose service selects `linux/arm64`, which matches this OS; no architecture change or OS reinstallation is needed. Raspberry Pi documents the Pi 3's ARM64 support in its [64-bit OS announcement](https://www.raspberrypi.com/news/raspberry-pi-os-64-bit/). Enable SSH and configure the network if needed. The examples below use hostname `iee305-pi.local`; replace it with your Pi's hostname or LAN IP, and replace `YOUR_PI_USER` with your chosen username.

For this small lecture example, the Pi hosts Zigbee2MQTT while EC2 hosts the broker and student connections. Keep other workloads light on the Pi and allow time for the first image download. If provisioning a fresh SD card later, Raspberry Pi OS Lite (64-bit) avoids running an unnecessary desktop; your existing 64-bit installation can be used as it is.

From **Windows PowerShell**, connect to the Pi:

```powershell
ssh YOUR_PI_USER@iee305-pi.local
```

On the **Pi**, confirm that `dpkg --print-architecture` reports `arm64`, then install Docker Engine and the Compose plugin using [Docker's Debian instructions](https://docs.docker.com/engine/install/debian/) for the Debian release underlying your Pi OS. Use the Debian `arm64` packages for this 64-bit OS. Complete Docker's documented group setup so your login user can run Docker, then reconnect your SSH session.

On the **Pi**:

```bash
dpkg --print-architecture
sudo apt update
sudo apt install git usbutils openssl python3-venv
sudo systemctl enable --now docker
docker info
docker compose version
```

Attach the antenna, then plug the ZBDongle-E into the Pi, preferably through a short USB extension away from USB 3 equipment and Wi-Fi antennas. Verify it on the **Pi**:

```bash
lsusb
ls -l /dev/serial/by-id/
```

Copy the SONOFF `/dev/serial/by-id/...` path into `local/.env`. This stable path is mapped to `/dev/ttyUSB0` inside the container, regardless of the host's numbered device name. The service uses Docker's explicit device mapping; no privileged container is required. The Pi must be able to connect outbound to the EC2 broker on TCP 8883, and its public egress IP must be allowed by the broker's security group.

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

Set `MQTT_HOST` to the exact endpoint passed to the EC2 setup script, `MQTT_PASSWORD` to the **instructor** MQTT password, and `ZIGBEE_DEVICE` to the actual Linux device path. The broker hostname is not `localhost`. Quoting the password with single quotes in `.env` preserves `$` and `#`; the example asks you to avoid single quotes in this password. The service reads the connection settings from Compose environment variables, which override the YAML values.

The generated public CA is not part of the Git checkout. Transfer this certificate through your Windows computer, so the EC2 private SSH key can stay on your computer. In **Windows PowerShell**, substitute the key path, EC2 hostname, and Pi login:

```powershell
scp -i 'C:\path\course-ec2.pem' ec2-user@ec2-REPLACE.compute.amazonaws.com:~/iee305-mqtt/ec2/runtime/certs/ca.crt "$env:TEMP\iee305-l20-ca.crt"
scp "$env:TEMP\iee305-l20-ca.crt" YOUR_PI_USER@iee305-pi.local:~/iee305-mqtt/local/certs/ca.crt
```

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

Keep that terminal open, then open [the frontend](http://localhost:8080) in your Windows browser. The tunnel connects your computer's port 8080 to the Pi's loopback port 8080. The frontend remains bound to loopback on the Pi; the Pi's LAN address on port 8080 is not the browser URL for this setup. Access to the Pi's SSH port 22 is required from the instructor computer.

On a new network, Zigbee2MQTT creates and saves random Zigbee keys and PAN IDs in `local/data/`. Preserve this folder between restarts; replacing it can require pairing devices again. The template selects Zigbee channel 20; check local Wi-Fi interference before pairing. Pairing starts closed. In the frontend, permit joining for a short interval, put a sensor into pairing mode, and close joining when done. Rename a sensor to `lecture_sensor` for a readable topic:

```text
iee305/l20/zigbee2mqtt/lecture_sensor
```

## 4. Give students the subscriber

Share the repository URL through Canvas, along with the public `ca.crt`, broker hostname, username `student`, and class password. Students need Git, Python 3.10+, and broker connectivity; they need no dongle, Docker, or AWS account. They clone the source using the commands below and save the supplied CA as `iee305-mqtt/students/ca.crt` before running the subscriber. This example uses a native MQTT client, not a browser WebSocket client.

In **Windows PowerShell**:

```powershell
git clone https://github.com/ptgrogan/iee305-mqtt.git
Set-Location iee305-mqtt/students
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe subscribe.py ec2-REPLACE.compute.amazonaws.com
```

Or in **Linux/macOS**:

```bash
git clone https://github.com/ptgrogan/iee305-mqtt.git
cd iee305-mqtt/students
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python subscribe.py ec2-REPLACE.compute.amazonaws.com
```

The password is entered at a hidden prompt. The default subscription shows device messages and bridge metadata. Narrow it with `--topic iee305/l20/zigbee2mqtt/lecture_sensor`. Each client gets a distinct broker-assigned ID; students should not all use the same fixed client ID.

The output contains the local **receipt time**, `retain`, QoS, topic, and JSON payload. A receipt timestamp is not the sensor's sampling time. The template also enables a device `last_seen` field. Some devices send on change or periodically; a quiet sensor is not necessarily disconnected. A retained message, when present, represents the broker's saved last value, not necessarily a fresh observation.

## 5. Rehearse access and the lecture demonstration

Before connecting hardware, install `students/requirements.txt` in a Python environment. From this example's root on the **Pi**, with the EC2 broker running and its CA copied locally:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r students/requirements.txt
.venv/bin/python check_access.py ec2-REPLACE.compute.amazonaws.com --ca local/certs/ca.crt
```

It prompts for both passwords and checks verified TLS, anonymous and bad-password login rejection, instructor publishing, student receipt, and a student publish rejected with MQTT 5 `Not authorized`. Test messages use a unique, non-retained `iee305/l20/access-check/...` topic, outside the Zigbee command path. A successful check verifies the configured broker without a USB dongle; still rehearse actual sensor reports separately.

Suggested live sequence:

1. Run two subscribers, then trigger a sensor. Trace device → coordinator → Zigbee2MQTT → EC2 broker → both subscribers.
2. Compare a wildcard subscription with a single device topic. Inspect JSON fields; their names depend on the device.
3. Discuss publishers, topics, subscriptions, and how the broker distributes a message without the sensor knowing subscribers' addresses.
4. Show that student credentials authenticate successfully while publishing is denied. Authentication and authorization are different checks.
5. If you have a controllable device, demonstrate a command from the instructor frontend. Zigbee2MQTT subscribes for commands and publishes state. Students remain observers.

## Operations and troubleshooting

- **Update source:** commit and push source changes from your development computer, then run `cd ~/iee305-mqtt` and `git pull --ff-only` on EC2 and the Pi. For an existing checkout, use this pull command instead of cloning again. Run `docker compose up -d` from `ec2/` or `local/` as appropriate after updating; restart the affected service when its mounted configuration changes. Git leaves ignored credentials and runtime state on each host. Keep `.env`, `ec2/runtime/`, and `local/data/` out of commits, and preserve them between updates. Run the EC2 `setup.sh` only for initial setup.
- **Rotate class access:** on EC2, `bash password.sh student`, followed by `docker compose restart mosquitto`. Restarting disconnects current clients as well as applying the new password. Update Canvas. Rotate `instructor` similarly, update `local/.env`, then run `docker compose up -d --force-recreate zigbee2mqtt` locally.
- **Renew the broker certificate:** before 90 days, on EC2 run the signing command below using the existing CA, CSR, and extension file. Clients keep the same CA. If the endpoint changed, create a new CSR and matching SAN extension first; update local/student hostnames too.
- **TLS failure:** hostname/IP must match the certificate SAN; use the correct `ca.crt`, check certificate expiry and client clocks. Keep certificate verification enabled.
- **Timeout:** check EC2's public endpoint, TCP 8883 security-group sources, campus outbound filtering, and `docker compose logs mosquitto`.
- **USB missing:** on the Pi, check power, the USB connection, `lsusb`, and the `/dev/serial/by-id/` path in `.env`. After unplugging and reconnecting the dongle, run `docker compose up -d --force-recreate zigbee2mqtt` on the Pi.
- **Ember startup error:** check coordinator firmware, baud rate, software flow control, and whether another process owns the adapter.
- **Computer port 8080 busy:** leave the Pi Compose file as supplied, use `ssh -N -L 8081:127.0.0.1:8080 YOUR_PI_USER@iee305-pi.local`, then browse to `http://localhost:8081`. If port 8080 is occupied on the Pi itself, change the Compose mapping to `127.0.0.1:8081:8080` and point the tunnel's destination at port 8081.
- **Stop the demonstration:** run `docker compose down` in each Compose directory. The broker volume and local Zigbee state are preserved. Stop/terminate EC2 and release unneeded paid resources separately.

Renew on **EC2**, from `ec2/`:

```bash
openssl x509 -req -sha256 -days 90 -in runtime/private/server.csr \
  -CA runtime/certs/ca.crt -CAkey runtime/private/ca.key -CAserial runtime/certs/ca.srl \
  -extfile runtime/private/server.ext -out runtime/certs/server.crt
sudo chgrp 1883 runtime/certs/server.crt
chmod 644 runtime/certs/server.crt
docker compose restart mosquitto
```

## References

- [AWS Docker installation on Amazon Linux 2023](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-docker.html)
- [Docker Compose plugin installation](https://docs.docker.com/compose/install/linux/)
- [Raspberry Pi setup and OS installation](https://www.raspberrypi.com/documentation/computers/getting-started.html)
- [Docker Engine for Debian / Raspberry Pi OS 64-bit](https://docs.docker.com/engine/install/debian/)
- [Zigbee2MQTT Docker/Compose installation](https://www.zigbee2mqtt.io/guide/installation/02_docker.html)
- [Zigbee2MQTT MQTT and TLS settings](https://www.zigbee2mqtt.io/guide/configuration/mqtt.html)
- [Zigbee2MQTT MQTT topics and messages](https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html)
- [Mosquitto password-file plugin](https://mosquitto.org/documentation/plugins/password-file/), [ACL-file plugin](https://mosquitto.org/documentation/plugins/acl-file/)
- [Paho MQTT Python client documentation](https://eclipse.dev/paho/clients/python/docs/)
