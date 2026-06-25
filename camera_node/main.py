"""
Pet Elevator — Pi Zero 2 W camera node.

Each landing has one of these units.  It captures frames from the CSI camera,
runs MobileNet SSD TFLite inference locally, and publishes a detection event
over MQTT when the dog is spotted.

Prerequisites on the Pi Zero 2 W:
  sudo apt install python3-picamera2 python3-paho-mqtt python3-pil python3-numpy
  pip install tflite-runtime

  # Download model (do this once):
  mkdir -p camera_node/models
  wget -O /tmp/model.zip https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
  unzip /tmp/model.zip detect.tflite labelmap.txt -d camera_node/models/

Environment variables:
  ELEVATOR_FLOOR=0|1          which floor this node watches (default 0)
  ELEVATOR_BROKER=<hostname>  Pi 4 MQTT broker hostname (default pet-elevator.local)

Run:
  ELEVATOR_FLOOR=0 python -m camera_node.main
"""

import json
import logging
import signal
import sys
import time

import numpy as np
import paho.mqtt.client as mqtt
from picamera2 import Picamera2

from . import config
from .detector import DogDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


class CameraNode:
    def __init__(self) -> None:
        self.detector   = DogDetector(
            model_path  = config.MODEL_PATH,
            labels_path = config.LABELS_PATH,
            num_threads = config.NUM_THREADS,
            input_size  = config.INPUT_SIZE,
        )
        self.camera     = self._init_camera()
        self.mqtt       = self._init_mqtt()
        self._running   = False

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self.camera.start()
        self.mqtt.connect_async(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
        self.mqtt.loop_start()
        self._running = True
        logger.info(
            "Camera node started — floor=%d, topic=%s",
            config.FLOOR, config.MQTT_TOPIC,
        )
        self._run_loop()

    def stop(self) -> None:
        self._running = False
        self.camera.stop()
        self.mqtt.loop_stop()
        self.mqtt.disconnect()
        logger.info("Camera node stopped")

    # ------------------------------------------------------------------ #
    # Main inference loop                                                  #
    # ------------------------------------------------------------------ #

    def _run_loop(self) -> None:
        while self._running:
            loop_start = time.monotonic()

            try:
                frame  = self.camera.capture_array()   # H×W×3 uint8 RGB
                score  = self.detector.detect(frame)
                logger.debug("Inference score: %.3f", score)

                if score >= config.MIN_SCORE:
                    self._publish(score)

            except Exception:
                logger.exception("Error during inference")

            # Sleep for the remainder of the configured interval
            elapsed = time.monotonic() - loop_start
            remaining = config.INFERENCE_INTERVAL - elapsed
            if remaining > 0:
                time.sleep(remaining)

    def _publish(self, score: float) -> None:
        payload = json.dumps({"floor": config.FLOOR, "confidence": round(score, 3)})
        result  = self.mqtt.publish(config.MQTT_TOPIC, payload, qos=0)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("Dog detected — published score=%.3f to %s", score, config.MQTT_TOPIC)
        else:
            logger.warning("MQTT publish failed (rc=%d)", result.rc)

    # ------------------------------------------------------------------ #
    # Setup helpers                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _init_camera() -> Picamera2:
        cam = Picamera2()
        cfg = cam.create_preview_configuration(
            main={"size": (config.FRAME_WIDTH, config.FRAME_HEIGHT), "format": "RGB888"}
        )
        cam.configure(cfg)
        return cam

    @staticmethod
    def _init_mqtt() -> mqtt.Client:
        client = mqtt.Client(
            client_id=f"elevator-camera-floor{config.FLOOR}",
            clean_session=True,
        )
        client.on_connect    = lambda c, u, f, rc: logger.info(
            "MQTT connected (rc=%d)", rc
        )
        client.on_disconnect = lambda c, u, rc: logger.warning(
            "MQTT disconnected (rc=%d)", rc
        )
        return client


def main() -> None:
    node = CameraNode()

    def shutdown(sig, frame) -> None:
        logger.info("Shutting down")
        node.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    node.start()


if __name__ == "__main__":
    main()
