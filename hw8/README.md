# HW-8 warehouse environmental monitoring

This instructor-operated publisher simulates three refrigerated warehouse zones. It requires the EC2 services but no Pi, Zigbee coordinator, physical sensor, or external API. Students only subscribe. The public source includes the scenario so the teaching data is inspectable; it contains no broker credentials or student solutions.

| File | Purpose |
| --- | --- |
| `scenario.py` | The fixed 24-sample episode for REF-01, REF-02, and REF-03, and the payload format |
| `publisher.py`, `Dockerfile`, `requirements.txt` | The `hw8-publisher` container, built by the `hw8` profile in `ec2/compose.yaml` on `python:3.12.16-slim` with `paho-mqtt` `2.1.0` |
| `capture.py` | Collects one complete cycle from received messages, skipping retained and duplicate deliveries |
| `check_hw8.py` | Live rehearsal as the `student` account |
| `test_hw8.py` | Offline tests of the scenario, collector, and publisher |
| `../ec2/prepare_hw8.sh` | Generates the publisher's MQTT credential on the EC2 host |

## Start on the existing EC2 host

From the `ec2` directory of the updated checkout:

```bash
bash prepare_hw8.sh
docker compose config --quiet
docker compose restart mosquitto
docker compose --profile hw8 up -d --build hw8-publisher
docker compose --profile hw8 ps
docker compose logs --tail=30 hw8-publisher
```

The first broker restart loads the new private listener and ACL. Connected lecture clients briefly disconnect and may reconnect. `prepare_hw8.sh` preserves both existing accounts and reuses its own generated secret on later runs. The publisher is in the `hw8` profile, so existing setup commands do not start it or require its secret. Its secret stays under ignored `ec2/runtime/hw8/`; distribute neither that directory nor the publisher credential. Keep it with the existing deployment state.

The publisher connects to Mosquitto's Docker-only TCP listener on 1883. Compose does not publish that port on the host. Student traffic continues to use verified TLS over WebSockets on 443; no new public port, DNS name, or student credential is needed.

The service restarts after process failure and on Docker restart. It retries initial connections and reconnects after broker interruptions. A publication rejection or acknowledgment timeout exits the process so Compose can restart it. The heartbeat healthcheck becomes unhealthy when no complete three-device update was acknowledged for 30 seconds; Docker's health status alone does not restart a running process.

## Topics and payload

Subscribe to `iee305/hw8/warehouse/REF-01` for one device or `iee305/hw8/warehouse/+` for all three. The student account can read `iee305/hw8/#` but cannot publish there. The `hw8-publisher` account can write only the three warehouse-device topics and has no read access. Instructor access includes HW-8.

The publisher retains one current observation per device. Every five seconds it publishes all three. A 120-second cycle has 24 samples per device. Values repeat from cycle to cycle; identifiers and UTC observation times advance with wall time. The unique observation key is `(device_id, cycle_id, sample_id)`. `sample_id` ranges from 1 to 24 within each cycle. Reconnection may replay a retained observation; QoS 1 may duplicate a delivery. Neither is an additional physical measurement.

Fields: `device_id` (string), `source` (`simulated`), `scenario_version` (`hw8-v1`), `cycle_id` (integer), `sample_id` (integer), `observed_at` (UTC ISO 8601 string), `temperature` (number in degrees Celsius), `humidity` (number in percent RH or null), and `door_open` (Boolean). MQTT topic, retained flag, and client receipt time are transport/client metadata and are not fields in the JSON payload.

Thresholds for this teaching exercise are temperature strictly above 8 C and humidity strictly above 65 percent RH. These are assignment settings, not a food safety specification. REF-01 remains ordinary; REF-02 has a door-open interval and a warming/recovery episode; REF-03 includes missing humidity and a valid 0 C reading.

## Rehearse and inspect

From the repository root, in the same Python environment as [Rehearse access](../README.md#7-rehearse-access):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r students/requirements.txt
.venv/bin/python hw8/test_hw8.py
.venv/bin/python hw8/check_hw8.py
```

`test_hw8.py` runs offline and needs no password. Run it after changing the scenario, publisher, or collector.

`check_hw8.py` prompts for the normal student password and connects over verified WebSockets/TLS on 443. It checks current retained observations, captures a complete cycle, validates the known scenario, and confirms a student cannot publish to a unique non-device access-check topic. It also verifies those forbidden bytes are not delivered. It never changes retained device data. A full capture may take up to roughly four minutes.

The browser client's Lecture 19 panel accepts the HW-8 filter in its `Subscribe to` field and shows the JSON in its message table. The L-20 Zigbee device cards remain specific to Zigbee2MQTT. A separate HW-8 dashboard is not required.

## Update, stop, and clean up

- **Update:** after `git pull --ff-only`, run `docker compose --profile hw8 up -d --build hw8-publisher` from `ec2/`. A plain `docker compose up -d` neither rebuilds nor restarts the publisher. After changing `mosquitto.conf` or `acl`, run `docker compose restart mosquitto`.
- **Stop publishing:** `docker compose --profile hw8 stop hw8-publisher`. Saved device values remain. For maintenance, leave the service running throughout the homework week, and inspect logs and health before release.
- **Stop everything:** use `docker compose --profile hw8 down`. A plain `docker compose down` leaves the publisher running and cannot remove the Compose network while it is attached.
- **Outage:** while the publisher is stopped, retained values can still arrive; check `observed_at`, not just receipt time. `capture.py`'s collector stops with an error after 270 seconds without a complete live cycle. Students keep that error as Part B evidence and contact the instructor; no offline recording is supplied in place of a live capture.
- **Remove retained values after the assignment:** stopping or disconnecting the publisher alone does not remove them. Stop the publisher first, or it restores them within five seconds. Then, from the repository root, with the instructor password:

```bash
.venv/bin/python clear_retained.py --topic "iee305/hw8/#" --dry-run
.venv/bin/python clear_retained.py --topic "iee305/hw8/#"
```
