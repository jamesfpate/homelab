#!/usr/bin/env python3
"""Next NYC subway arrivals at a stop -> MQTT, for the office clock / Home Assistant.

Polls the MTA GTFS-realtime feed (no API key needed) every POLL_S seconds and publishes a retained JSON message:
  {"route": "Q", "stop": "D27N", "minutes": [4, 10, 22], "times": ["2026-10-14T08:16:00", ...], "updated": "..."}
Env: FEED (nqrw|ace|bdfm|g|jz|l|si|"" for 1-7), ROUTE, STOP_ID (GTFS stop id incl. N/S), MQTT_HOST, MQTT_USER,
MQTT_PASS, TOPIC, POLL_S, MAX_TRAINS.
"""

import json
import os
import time
from datetime import datetime

import paho.mqtt.client as mqtt
import requests
from google.transit import gtfs_realtime_pb2

FEED = os.environ.get("FEED", "nqrw")
ROUTE = os.environ.get("ROUTE", "Q")
STOP_ID = os.environ.get("STOP_ID", "D27N")
TOPIC = os.environ.get("TOPIC", "transit/beverley_q_manhattan")
POLL_S = int(os.environ.get("POLL_S", "30"))
MAX_TRAINS = int(os.environ.get("MAX_TRAINS", "4"))
URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs" + (f"-{FEED}" if FEED else "")


def next_arrivals() -> list[float]:
    r = requests.get(URL, timeout=20, headers={"User-Agent": "homelab-mta-trains/1.0"})
    r.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(r.content)
    now = time.time()
    arrivals = []
    for ent in feed.entity:
        if not ent.HasField("trip_update") or ent.trip_update.trip.route_id != ROUTE:
            continue
        for stu in ent.trip_update.stop_time_update:
            if stu.stop_id == STOP_ID:
                t = stu.arrival.time or stu.departure.time
                if t and t - now > -30:
                    arrivals.append(t)
    return sorted(arrivals)[:MAX_TRAINS]


def main() -> None:
    # Client id must be unique per watcher, or the broker drops the other one every second (and fires its "offline" will).
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mta-" + TOPIC.replace("/", "-"))
    client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])
    client.will_set(TOPIC + "/status", "offline", retain=True)
    client.connect(os.environ.get("MQTT_HOST", "127.0.0.1"), int(os.environ.get("MQTT_PORT", "1883")), keepalive=60)
    client.loop_start()
    client.publish(TOPIC + "/status", "online", retain=True)
    while True:
        try:
            arrivals = next_arrivals()
            now = time.time()
            payload = {
                "route": ROUTE, "stop": STOP_ID,
                "minutes": [max(0, int(round((t - now) / 60))) for t in arrivals],
                "times": [datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds") for t in arrivals],
                "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            client.publish(TOPIC, json.dumps(payload), retain=True)
            print(f"{payload['updated']} {ROUTE}@{STOP_ID}: {payload['minutes']}", flush=True)
        except Exception as e:  # feed hiccup: keep the last retained value, try again next round
            print(f"{datetime.now().isoformat(timespec='seconds')} error: {e}", flush=True)
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
