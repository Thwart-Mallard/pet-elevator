import os

# ── Floor identity ────────────────────────────────────────────────────────────
# Set ELEVATOR_FLOOR=0 or =1 in the environment (or /etc/environment) on each
# Pi Zero 2 W so both units can run identical code.
FLOOR = int(os.environ.get("ELEVATOR_FLOOR", "0"))

# ── Camera ────────────────────────────────────────────────────────────────────
FRAME_WIDTH  = 640
FRAME_HEIGHT = 480

# ── TFLite model ──────────────────────────────────────────────────────────────
# Download:
#   wget https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
#   unzip it into camera_node/models/
MODEL_PATH  = os.path.join(os.path.dirname(__file__), "models", "detect.tflite")
LABELS_PATH = os.path.join(os.path.dirname(__file__), "models", "labelmap.txt")

INPUT_SIZE   = 300          # MobileNet SSD expects 300×300
NUM_THREADS  = 4            # use all cores on the Zero 2 W

# ── Detection ─────────────────────────────────────────────────────────────────
# Minimum score to publish a detection event.  The Pi 4 controller applies its
# own 0.80 threshold; using 0.50 here avoids discarding borderline frames before
# they can be logged on the controller side.
MIN_SCORE           = 0.50
INFERENCE_INTERVAL  = 2.0   # seconds between inference runs (Zero 2 W is ~1 fps on this model)

# ── MQTT ──────────────────────────────────────────────────────────────────────
MQTT_BROKER = os.environ.get("ELEVATOR_BROKER", "pet-elevator.local")
MQTT_PORT   = 1883
MQTT_TOPIC  = f"elevator/camera/floor{FLOOR}/detection"
