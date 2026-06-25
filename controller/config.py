# BCM GPIO pin assignments (Pi 4)
STEP_PIN    = 18   # → DM542T PUL+ (common cathode wiring)
DIR_PIN     = 23   # → DM542T DIR+
ENABLE_PIN  = 24   # → DM542T ENA+  (LOW = motor enabled, HIGH = disabled)

# NC limit switches & e-stop — all pulled HIGH internally.
# Switch CLOSED (normal): pin reads LOW.  Switch OPEN (at limit / wire fault): pin reads HIGH.
LIMIT_BOTTOM_PIN = 17
LIMIT_TOP_PIN    = 27
ESTOP_PIN        = 22

# DM542T step direction convention — swap if carriage moves the wrong way
DIR_UP   = 1
DIR_DOWN = 0

# Motion parameters
STEPS_PER_MM    = 135.81
TOTAL_TRAVEL_MM = 3048.0
TOTAL_STEPS     = int(STEPS_PER_MM * TOTAL_TRAVEL_MM)   # 413,906

MAX_SPEED_MM_S  = 25.0
ACCEL_MM_S2     = 8.0
HOMING_SPEED_MM_S = 5.0

MAX_SPEED_STEPS_S   = MAX_SPEED_MM_S   * STEPS_PER_MM   # ~3395 steps/s
ACCEL_STEPS_S2      = ACCEL_MM_S2      * STEPS_PER_MM   # ~1086 steps/s²
HOMING_STEPS_S      = HOMING_SPEED_MM_S * STEPS_PER_MM  # ~679  steps/s

# Floor positions (steps from home / bottom)
FLOOR_POSITIONS = {
    0: 0,            # Ground floor (home)
    1: TOTAL_STEPS,  # Upper floor
}

# MQTT (broker runs on this Pi 4)
MQTT_BROKER         = "localhost"
MQTT_PORT           = 1883
MQTT_TOPIC_COMMAND  = "elevator/command"   # subscribe: {"floor": 0|1}
MQTT_TOPIC_STATUS   = "elevator/status"    # publish:  state/position
MQTT_TOPIC_DETECTION = "elevator/camera/+/detection"  # from Zero 2 W nodes

# Wiring note:
# Common-cathode wiring — DM542T PUL-, DIR-, ENA- tied to GND; Pi GPIO drives the + sides.
# At 3.3 V: I = (3.3 - 1.2) / 220 ≈ 9.5 mA through the optocouplers (DM542T specifies 10 mA
# minimum).  If you see missed steps, add a BSS138 level-shifter to bring signals to 5 V.
