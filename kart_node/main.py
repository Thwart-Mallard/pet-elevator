"""
Pet Elevator — Kart sensor node (Pi Zero 2 W on the elevator kart).

Monitors a door switch (NC) and a pressure mat (NO) via GPIO and publishes
their state to the MQTT broker over WiFi with retained messages, so the Pi 4B
always has the current kart state even after a reconnect.

Safety behaviour (enforced on the Pi 4B controller):
  - Elevator will not move while door is reported open.
  - Door opening during transit triggers an immediate motor stop and fault.
  - Pressure mat confirms the dog has boarded before the door is closed.

Prerequisites on the kart Pi Zero 2 W:
  sudo apt install python3-paho-mqtt python3-rpi.gpio

Environment variable:
  ELEVATOR_BROKER=<hostname>  Pi 4B MQTT broker (default pet-elevator.local)

Run:
  python -m kart_node.main
"""

import json
import logging
import signal
import sys
import time

import RPi.GPIO as GPIO
import paho.mqtt.client as mqtt

from . import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


class KartNode:
    def __init__(self) -> None:
        self._mqtt = self._init_mqtt()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._setup_gpio()
        self._mqtt.connect_async(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
        self._mqtt.loop_start()
        # Give MQTT a moment to connect before publishing initial state
        time.sleep(2)
        self._publish_door(self._read_door())
        self._publish_pressure(self._read_pressure())
        logger.info(
            "Kart node running — door=%s, dog_present=%s",
            self._read_door(), self._read_pressure(),
        )
        signal.pause()  # block until SIGTERM / SIGINT

    def stop(self) -> None:
        GPIO.cleanup()
        self._mqtt.loop_stop()
        self._mqtt.disconnect()
        logger.info("Kart node stopped")

    # ------------------------------------------------------------------ #
    # GPIO                                                                 #
    # ------------------------------------------------------------------ #

    def _setup_gpio(self) -> None:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.DOOR_PIN,     GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(config.PRESSURE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(
            config.DOOR_PIN, GPIO.BOTH,
            callback=self._on_door_change, bouncetime=50,
        )
        GPIO.add_event_detect(
            config.PRESSURE_PIN, GPIO.BOTH,
            callback=self._on_pressure_change, bouncetime=200,
        )

    def _read_door(self) -> str:
        return "closed" if GPIO.input(config.DOOR_PIN) == GPIO.LOW else "open"

    def _read_pressure(self) -> bool:
        return GPIO.input(config.PRESSURE_PIN) == GPIO.HIGH

    def _on_door_change(self, channel: int) -> None:
        status = self._read_door()
        logger.info("Door → %s", status)
        self._publish_door(status)

    def _on_pressure_change(self, channel: int) -> None:
        present = self._read_pressure()
        logger.info("Pressure mat → dog_present=%s", present)
        self._publish_pressure(present)

    # ------------------------------------------------------------------ #
    # MQTT                                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _init_mqtt() -> mqtt.Client:
        client = mqtt.Client(client_id="elevator-kart", clean_session=True)
        client.on_connect    = lambda c, u, f, rc: logger.info(
            "MQTT connected to %s (rc=%d)", config.MQTT_BROKER, rc
        )
        client.on_disconnect = lambda c, u, rc: logger.warning(
            "MQTT disconnected (rc=%d)", rc
        )
        return client

    def _publish_door(self, status: str) -> None:
        payload = json.dumps({"status": status})
        self._mqtt.publish(config.MQTT_TOPIC_DOOR, payload, qos=1, retain=True)
        logger.debug("Published %s → %s", config.MQTT_TOPIC_DOOR, payload)

    def _publish_pressure(self, present: bool) -> None:
        payload = json.dumps({"dog_present": present})
        self._mqtt.publish(config.MQTT_TOPIC_PRESSURE, payload, qos=1, retain=True)
        logger.debug("Published %s → %s", config.MQTT_TOPIC_PRESSURE, payload)


def main() -> None:
    node = KartNode()

    def shutdown(sig, frame) -> None:
        logger.info("Shutting down")
        node.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    node.start()


if __name__ == "__main__":
    main()
