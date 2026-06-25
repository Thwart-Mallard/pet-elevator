import os

# ── GPIO pins (BCM numbering) ──────────────────────────────────────────────
# Door switch: NC microswitch on the kart door frame.
#   Pull-up enabled. Door closed (normal) = LOW. Door open = HIGH.
DOOR_PIN     = 17

# Pressure mat: NO contact pad on the kart floor.
#   Pull-down enabled. No dog = LOW. Dog on mat = HIGH.
PRESSURE_PIN = 27

# Door actuator: 2-channel relay module (active-LOW) driving a linear actuator.
#   GPIO LOW  = relay energised = actuator moving.
#   GPIO HIGH = relay off       = actuator holds position.
#   Software guarantees only one relay is ever energised at a time.
DOOR_RELAY_OPEN_PIN  = 5   # relay IN1 → extend actuator (open door)
DOOR_RELAY_CLOSE_PIN = 6   # relay IN2 → retract actuator (close door)

# Tune to your actuator's stroke length and no-load speed; add ~0.5 s margin.
DOOR_ACTUATOR_STROKE_TIME = 4.0  # seconds

# How long the pressure mat must be continuously held before publishing "dog aboard".
# Prevents a brief step-on from triggering the door-close sequence prematurely.
DOG_BOARD_SETTLE_TIME = 3.0  # seconds

# ── MQTT ──────────────────────────────────────────────────────────────────
MQTT_BROKER           = os.environ.get("ELEVATOR_BROKER", "pet-elevator.local")
MQTT_PORT             = 1883
MQTT_TOPIC_DOOR       = "elevator/kart/door"           # retained
MQTT_TOPIC_PRESSURE   = "elevator/kart/pressure"       # retained
MQTT_TOPIC_DOOR_CMD   = "elevator/kart/door/command"   # subscribe: {"action": "open"|"close"}
