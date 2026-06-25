import os

# ── GPIO pins (BCM numbering) ──────────────────────────────────────────────
# Door switch: NC microswitch on the kart door frame.
#   Pull-up enabled. Door closed (normal) = LOW. Door open = HIGH.
DOOR_PIN     = 17

# Pressure mat: NO contact pad on the kart floor.
#   Pull-down enabled. No dog = LOW. Dog on mat = HIGH.
PRESSURE_PIN = 27

# ── MQTT ──────────────────────────────────────────────────────────────────
MQTT_BROKER           = os.environ.get("ELEVATOR_BROKER", "pet-elevator.local")
MQTT_PORT             = 1883
MQTT_TOPIC_DOOR       = "elevator/kart/door"      # retained
MQTT_TOPIC_PRESSURE   = "elevator/kart/pressure"  # retained
