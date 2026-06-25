import json
import logging
import os
import queue
import threading

import paho.mqtt.client as mqtt
from flask import Flask, Response, jsonify, render_template, request

from . import config

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


class WebUI:
    """
    Flask web UI served on port 8080.

    Has its own paho-mqtt connection to the local broker so it is fully
    decoupled from the controller's MQTTClient:
      - Subscribes to elevator/status  → pushes updates to SSE clients
      - Publishes to elevator/command  → forwards button presses

    SSE (Server-Sent Events) gives real-time status to every connected
    browser without polling.  A heartbeat comment is sent every 25 s to
    keep proxies and mobile browsers from closing the connection.
    """

    def __init__(self) -> None:
        self._status: dict = {"state": "boot", "floor": None, "position": None}
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()

        self._mqtt = mqtt.Client(client_id="elevator-webui", clean_session=True)
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_message = self._on_message
        self._mqtt.on_disconnect = lambda c, u, rc: logger.warning(
            "Web UI MQTT disconnected (rc=%d)", rc
        )

        self.app = Flask(__name__, template_folder=_TEMPLATE_DIR)
        self.app.logger.setLevel(logging.WARNING)   # suppress Flask request logs
        self._register_routes()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        self._mqtt.connect_async(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
        self._mqtt.loop_start()

        threading.Thread(
            target=self.app.run,
            kwargs=dict(host=host, port=port, threaded=True, use_reloader=False),
            daemon=True,
        ).start()
        logger.info("Web UI available at http://pet-elevator.local:%d", port)

    def stop(self) -> None:
        self._mqtt.loop_stop()
        self._mqtt.disconnect()

    # ------------------------------------------------------------------ #
    # MQTT                                                                 #
    # ------------------------------------------------------------------ #

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            client.subscribe(config.MQTT_TOPIC_STATUS, qos=1)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            status = json.loads(msg.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        with self._lock:
            self._status = status
            subscribers = list(self._subscribers)

        payload = json.dumps(status)
        for q in subscribers:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass

    # ------------------------------------------------------------------ #
    # Routes                                                               #
    # ------------------------------------------------------------------ #

    def _register_routes(self) -> None:
        app = self.app

        @app.route("/")
        def index():
            return render_template("index.html", total_steps=config.TOTAL_STEPS)

        @app.route("/api/status")
        def api_status():
            with self._lock:
                return jsonify(self._status)

        @app.route("/api/command", methods=["POST"])
        def api_command():
            data = request.get_json(force=True, silent=True)
            if not data or "action" not in data:
                return jsonify({"ok": False, "error": "missing action"}), 400
            self._mqtt.publish(
                config.MQTT_TOPIC_COMMAND, json.dumps(data), qos=1
            )
            return jsonify({"ok": True})

        @app.route("/api/door", methods=["POST"])
        def api_door():
            data = request.get_json(force=True, silent=True)
            if not data or data.get("action") not in ("open", "close"):
                return jsonify({"ok": False, "error": "action must be 'open' or 'close'"}), 400
            self._mqtt.publish(
                config.MQTT_TOPIC_KART_DOOR_CMD, json.dumps(data), qos=1
            )
            return jsonify({"ok": True})

        @app.route("/api/events")
        def api_events():
            def stream():
                q: queue.Queue = queue.Queue(maxsize=20)
                with self._lock:
                    self._subscribers.append(q)
                    current = json.dumps(self._status)
                try:
                    yield f"data: {current}\n\n"
                    while True:
                        try:
                            data = q.get(timeout=25)
                            yield f"data: {data}\n\n"
                        except queue.Empty:
                            yield ": heartbeat\n\n"
                finally:
                    with self._lock:
                        if q in self._subscribers:
                            self._subscribers.remove(q)

            return Response(
                stream(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
