import json
import logging
import paho.mqtt.client as mqtt

from . import config

logger = logging.getLogger(__name__)

# Minimum confidence from the camera node to act on a detection
DETECTION_CONFIDENCE_THRESHOLD = 0.80


class MQTTClient:
    """
    Thin paho-mqtt wrapper.

    Subscribes to:
      elevator/command              {"action": "go"|"home"|"reset", "floor": 0|1}
      elevator/camera/+/detection   {"floor": 0|1, "confidence": 0.0-1.0}
      elevator/kart/door            {"status": "open"|"closed"}
      elevator/kart/pressure        {"dog_present": true|false}

    Publishes to:
      elevator/status         {"state": "...", "floor": ..., "position": ...,
                               "kart_door": "...", "dog_present": ...}
    """

    def __init__(self, fsm) -> None:
        self.fsm = fsm
        self._client = mqtt.Client(client_id="elevator-controller", clean_session=True)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message

    def start(self) -> None:
        self._client.connect_async(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish_status(self, status: dict) -> None:
        self._client.publish(
            config.MQTT_TOPIC_STATUS,
            json.dumps(status),
            qos=1,
            retain=True,
        )

    # ------------------------------------------------------------------ #
    # paho callbacks (run on the paho network thread)                     #
    # ------------------------------------------------------------------ #

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            logger.error("MQTT connection failed: rc=%d", rc)
            return

        logger.info("MQTT connected to %s:%d", config.MQTT_BROKER, config.MQTT_PORT)
        client.subscribe(config.MQTT_TOPIC_COMMAND,       qos=1)
        client.subscribe(config.MQTT_TOPIC_DETECTION,     qos=0)
        client.subscribe(config.MQTT_TOPIC_KART_DOOR,     qos=1)
        client.subscribe(config.MQTT_TOPIC_KART_PRESSURE, qos=1)

        # Publish current status immediately on (re)connect so retained message is fresh
        self.publish_status(self.fsm.status)

    def _on_disconnect(self, client, userdata, rc) -> None:
        if rc != 0:
            logger.warning("MQTT unexpectedly disconnected (rc=%d) — will auto-reconnect", rc)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Unparseable MQTT message on %s: %r", msg.topic, msg.payload)
            return

        if msg.topic == config.MQTT_TOPIC_COMMAND:
            self._handle_command(payload)
        elif "/detection" in msg.topic:
            self._handle_detection(msg.topic, payload)
        elif msg.topic == config.MQTT_TOPIC_KART_DOOR:
            self._handle_kart_door(payload)
        elif msg.topic == config.MQTT_TOPIC_KART_PRESSURE:
            self._handle_kart_pressure(payload)

    def _handle_command(self, payload: dict) -> None:
        action = payload.get("action")
        if action == "go":
            floor = payload.get("floor")
            if floor in (0, 1):
                logger.info("Command: go to floor %d", floor)
                self.fsm.cmd_go(floor)
            else:
                logger.warning("Command: invalid floor %r", floor)
        elif action == "home":
            logger.info("Command: home")
            self.fsm.cmd_home()
        elif action == "reset":
            logger.info("Command: reset")
            self.fsm.cmd_reset()
        elif action == "estop":
            logger.warning("Command: e-stop via web UI")
            self.fsm.on_safety_fault("web_estop")
        else:
            logger.warning("Command: unknown action %r", action)

    def _handle_kart_door(self, payload: dict) -> None:
        status = payload.get("status")
        if status not in ("open", "closed"):
            logger.warning("Malformed kart door payload: %r", payload)
            return
        logger.info("Kart door: %s", status)
        self.fsm.on_kart_door(status)

    def _handle_kart_pressure(self, payload: dict) -> None:
        present = payload.get("dog_present")
        if not isinstance(present, bool):
            logger.warning("Malformed kart pressure payload: %r", payload)
            return
        logger.info("Kart pressure mat: dog_present=%s", present)
        self.fsm.on_kart_pressure(present)

    def _handle_detection(self, topic: str, payload: dict) -> None:
        """
        Camera node reports dog detected.
        Only call the elevator if confidence clears the threshold and the
        elevator is already idle (FSM ignores the command otherwise).
        """
        confidence = payload.get("confidence", 0.0)
        floor      = payload.get("floor")

        if not isinstance(confidence, (int, float)) or floor not in (0, 1):
            logger.warning("Malformed detection payload: %r", payload)
            return

        if confidence < DETECTION_CONFIDENCE_THRESHOLD:
            logger.debug("Detection on %s below threshold: %.2f", topic, confidence)
            return

        logger.info("Dog detected at floor %d (confidence=%.2f) — requesting elevator", floor, confidence)
        self.fsm.cmd_go(floor)
