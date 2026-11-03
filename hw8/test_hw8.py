"""Offline HW-8 regression checks. Run: python hw8/test_hw8.py"""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from capture import collect_cycle
from scenario import BASE_TOPIC, DEVICES, cycle_readings, make_reading


def envelopes(cycle):
    return [{"topic": f"{BASE_TOPIC}/{data['device_id']}",
             "text": json.dumps(data), "retained": False,
             "received_at": "test receipt timestamp"}
            for data in cycle_readings(cycle)]


class ScenarioTests(unittest.TestCase):
    def test_schema_keys_times_and_measurements(self):
        rows = list(cycle_readings(14945550))
        self.assertEqual(len(rows), 72)
        keys = set()
        for data in rows:
            self.assertEqual(set(data), {"device_id", "source", "scenario_version", "cycle_id",
                                         "sample_id", "observed_at", "temperature", "humidity", "door_open"})
            self.assertEqual(data["source"], "simulated")
            self.assertEqual(data["scenario_version"], "hw8-v1")
            self.assertIs(type(data["cycle_id"]), int)
            self.assertIs(type(data["sample_id"]), int)
            self.assertIs(type(data["door_open"]), bool)
            stamp = datetime.fromisoformat(data["observed_at"].replace("Z", "+00:00"))
            self.assertEqual(stamp.tzinfo, timezone.utc)
            self.assertEqual(stamp.timestamp(), data["cycle_id"] * 120 + (data["sample_id"] - 1) * 5)
            keys.add((data["device_id"], data["cycle_id"], data["sample_id"]))
        self.assertEqual(len(keys), 72)

    def test_repetition_keeps_values_and_advances_identity(self):
        a = make_reading("REF-02", 100, 10)
        b = make_reading("REF-02", 101, 10)
        self.assertEqual(a["temperature"], b["temperature"])
        self.assertNotEqual(a["cycle_id"], b["cycle_id"])
        self.assertNotEqual(a["observed_at"], b["observed_at"])
        self.assertEqual(make_reading("REF-03", 100, 5)["temperature"], 0.0)
        self.assertIsNone(make_reading("REF-03", 100, 9)["humidity"])
        self.assertFalse(make_reading("REF-02", 100, 13)["door_open"])

    def test_invalid_device_or_position(self):
        for device, sample in [("UNKNOWN", 1), ("REF-01", 0), ("REF-01", 25)]:
            with self.assertRaises(ValueError):
                make_reading(device, 100, sample)


class CaptureTests(unittest.TestCase):
    def test_retained_values_and_duplicates_are_excluded(self):
        retained = envelopes(99)
        for row in retained:
            row["retained"] = True
        live = envelopes(100)
        duplicated = [row for message in live for row in (message, message.copy())]
        selected = collect_cycle(retained + duplicated, timeout=1)
        self.assertEqual(len(selected), 72)
        self.assertTrue(all(not row["retained"] for row in selected))
        self.assertEqual({json.loads(row["text"])["cycle_id"] for row in selected}, {100})
        self.assertEqual(json.loads(selected[0]["text"])["device_id"], "REF-01")

    def test_partial_cycle_is_not_mixed_with_next_cycle(self):
        partial = envelopes(100)[15:]
        selected = collect_cycle(partial + envelopes(101), timeout=1)
        self.assertEqual({json.loads(row["text"])["cycle_id"] for row in selected}, {101})

    def test_interrupted_cycle_restarts_at_new_boundary(self):
        selected = collect_cycle(envelopes(100)[:30] + envelopes(101), timeout=1)
        self.assertEqual(len(selected), 72)
        self.assertEqual({json.loads(row["text"])["cycle_id"] for row in selected}, {101})

    def test_missing_stream_times_out(self):
        with self.assertRaises(TimeoutError):
            collect_cycle([], timeout=0)


class PublisherTests(unittest.TestCase):
    def exercise(self, refused=False, failed_publish=False):
        import publisher
        import paho.mqtt.client as mqtt
        from paho.mqtt.packettypes import PacketTypes
        from paho.mqtt.reasoncodes import ReasonCode

        class EndTest(Exception):
            pass

        class Client:
            def __init__(self):
                self.sent = []
                self.closed = False
                self.stopped = False

            def username_pw_set(self, username, password):
                self.username = username

            def reconnect_delay_set(self, **kwargs):
                pass

            def connect_async(self, host, port, keepalive):
                self.host, self.port = host, port

            def loop_start(self):
                name = "Not authorized" if refused else "Success"
                self.on_connect(self, None, None, ReasonCode(PacketTypes.CONNACK, name), None)

            def publish(self, topic, payload, qos, retain):
                self.sent.append((topic, json.loads(payload), qos, retain))
                self.on_publish(self, None, len(self.sent), ReasonCode(PacketTypes.PUBACK, "Success"), None)
                class Info:
                    def wait_for_publish(self, timeout):
                        pass
                    def is_published(self):
                        return not failed_publish
                return Info()

            def disconnect(self):
                self.closed = True

            def loop_stop(self):
                self.stopped = True

        client = Client()
        with tempfile.TemporaryDirectory() as directory:
            password = Path(directory) / 'password'
            password.write_text('test-only-not-a-live-secret')
            with patch.dict('os.environ', {"MQTT_PASSWORD_FILE": str(password)}), \
                 patch.object(publisher.mqtt, 'Client', return_value=client), \
                 patch.object(publisher.signal, 'signal'), \
                 patch.object(publisher.time, 'time', return_value=12000), \
                 patch.object(publisher.Path, 'touch', side_effect=EndTest):
                expected = RuntimeError if refused or failed_publish else EndTest
                with self.assertRaises(expected):
                    publisher.main()
        self.assertTrue(client.closed and client.stopped)
        if not refused and not failed_publish:
            self.assertEqual(len(client.sent), 3)
            self.assertEqual({row[0] for row in client.sent}, {f"{BASE_TOPIC}/{d}" for d in DEVICES})
            self.assertTrue(all(qos == 1 and retain for _, _, qos, retain in client.sent))
            self.assertTrue(all(row[1]["sample_id"] == 1 and row[1]["cycle_id"] == 100 for row in client.sent))

    def test_acknowledged_three_device_publication(self):
        self.exercise()

    def test_rejected_login_exits_for_supervisor_restart(self):
        self.exercise(refused=True)

    def test_unacknowledged_publication_exits(self):
        self.exercise(failed_publish=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
