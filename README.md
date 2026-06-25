# Pet Elevator

A two-floor cable-winch lift for an ageing dog with mobility difficulties.

A Raspberry Pi 4 drives a NEMA 23 stepper motor via a DM542T driver. Two Pi Zero 2 W camera nodes watch each landing and call the elevator automatically when the dog is detected. Everything is controllable from a browser on the home network.

![Web UI](docs/web_ui_screenshot.png)

---

## Hardware

| Component | Part |
|-----------|------|
| Controller | Raspberry Pi 4 |
| Motor | NEMA 23, 3 N·m |
| Driver | DM542T (1/16 microstep, 24 V) |
| Gearbox | 10:1 worm gear (self-locking) |
| Drum | 75 mm diameter |
| Camera nodes | Raspberry Pi Zero 2 W × 2 + CSI camera |
| Safety inputs | 2× NC limit switches, NC latching e-stop |

Full wiring diagram: [`wiring/wiring_diagram.svg`](wiring/wiring_diagram.svg)

---

## Quick Start

### Pi 4 — Controller

```bash
# 1. Install dependencies
sudo apt update
sudo apt install -y pigpio python3-pigpio python3-paho-mqtt \
                    python3-pil python3-numpy mosquitto
pip install flask

# 2. Enable services
sudo systemctl enable --now pigpiod mosquitto

# 3. Clone the repo
git clone https://github.com/Thwart-Mallard/pet-elevator /home/pi/pet-elevator
cd /home/pi/pet-elevator

# 4. Install and enable the systemd service
sudo cp deploy/elevator-controller.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable elevator-controller
```

Start the controller (after wiring checks):

```bash
sudo systemctl start elevator-controller
journalctl -u elevator-controller -f
```

Open the web UI on any phone or browser on the home network:

```
http://pet-elevator.local:8080
```

---

### Pi Zero 2 W — Camera Node (repeat for each unit)

```bash
# 1. Enable camera
sudo raspi-config   # Interface Options → Camera → Enable
sudo reboot

# 2. Install dependencies
sudo apt update
sudo apt install -y python3-picamera2 python3-paho-mqtt python3-pil python3-numpy
pip install tflite-runtime

# 3. Download TFLite model
mkdir -p /home/pi/pet-elevator/camera_node/models
cd /tmp
wget https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
unzip coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip \
      detect.tflite labelmap.txt \
      -d /home/pi/pet-elevator/camera_node/models/

# 4. Set floor identity
sudo cp /home/pi/pet-elevator/deploy/elevator-camera.env /etc/default/elevator-camera
sudo nano /etc/default/elevator-camera
# Set ELEVATOR_FLOOR=0 (ground) or 1 (upper)
# Set ELEVATOR_BROKER=pet-elevator.local

# 5. Install and start the service
sudo cp /home/pi/pet-elevator/deploy/elevator-camera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now elevator-camera
```

---

## MQTT API

All messages are JSON. Broker runs on the Pi 4 (port 1883).

| Topic | Direction | Example payload |
|-------|-----------|-----------------|
| `elevator/command` | → controller | `{"action": "go", "floor": 1}` |
| `elevator/command` | → controller | `{"action": "home"}` |
| `elevator/command` | → controller | `{"action": "estop"}` |
| `elevator/command` | → controller | `{"action": "reset"}` |
| `elevator/status` | ← controller | `{"state": "idle", "floor": 1, "position": 413906}` |
| `elevator/camera/floor0/detection` | ← camera node | `{"score": 0.91, "floor": 0}` |

Send a command from any machine on the network:

```bash
mosquitto_pub -h pet-elevator.local -t elevator/command \
  -m '{"action": "go", "floor": 1}'
```

---

## Project Structure

```
pet-elevator/
├── controller/          # Pi 4 — motor, FSM, MQTT, web UI
│   ├── config.py        # GPIO pins, speeds, MQTT settings
│   ├── motor.py         # DMA stepper control (pigpio waves)
│   ├── safety.py        # NC switch callbacks
│   ├── state_machine.py # Elevator FSM
│   ├── mqtt_client.py   # paho-mqtt wrapper
│   ├── web_ui.py        # Flask web UI (port 8080, SSE)
│   ├── templates/
│   │   └── index.html   # Mobile-friendly control interface
│   └── main.py          # Entry point
├── camera_node/         # Pi Zero 2 W — TFLite dog detection
│   ├── config.py
│   ├── detector.py
│   └── main.py
├── deploy/              # systemd service units
├── docs/                # Full documentation
│   ├── 01_project_overview.md
│   ├── 02_hardware.md
│   ├── 03_software_architecture.md
│   └── 04_getting_started.md
└── wiring/
    └── wiring_diagram.svg
```

---

## Documentation

- [Project Overview](docs/01_project_overview.md) — design decisions, physical spec
- [Hardware](docs/02_hardware.md) — BOM, GPIO table, DM542T DIP switch settings
- [Software Architecture](docs/03_software_architecture.md) — module map, state machine, MQTT API, web UI
- [Getting Started](docs/04_getting_started.md) — full installation and first-run guide
