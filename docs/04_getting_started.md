# Getting Started

## Prerequisites

- All hardware assembled and wired per `wiring/wiring_diagram.svg`
- Raspberry Pi 4B running Raspberry Pi OS (Bookworm or later)
- Two Raspberry Pi Zero 2 W, each with a CSI camera module fitted (one per landing)
- One Raspberry Pi Zero 2 W for the kart sensor node (no camera)
- Home WiFi network — all four Pis on the same network
- 24V PSU **not yet connected** for initial software setup

---

## Pi 4B Setup

### 1. Install system dependencies

```bash
sudo apt update
sudo apt install -y pigpio python3-pigpio python3-paho-mqtt \
                    python3-pil python3-numpy mosquitto
pip install flask
```

Enable and start the services:

```bash
sudo systemctl enable pigpiod mosquitto
sudo systemctl start  pigpiod mosquitto
```

### 2. Clone / copy the project

```bash
git clone <your-repo-url> /home/pi/pet-elevator
cd /home/pi/pet-elevator
```

Or copy the project directory by other means. The working directory should be
`/home/pi/pet-elevator` (adjustable in the systemd service file).

### 3. Set the Pi 4B hostname (optional but recommended)

```bash
sudo raspi-config   # → System Options → Hostname → pet-elevator
```

The kart camera node resolves the broker at `pet-elevator.local` by default.

### 4. Install the systemd service

```bash
sudo cp deploy/elevator-controller.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable elevator-controller
```

Do **not** start it yet — complete the wiring checks first (Step 7).

---

## Pi Zero 2 W Setup — Landing Camera Nodes (repeat for each unit)

### 1. Enable the camera interface

```bash
sudo raspi-config   # → Interface Options → Camera → Enable
sudo reboot
```

### 2. Install dependencies

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-paho-mqtt python3-pil python3-numpy
pip install tflite-runtime
```

### 3. Download the TFLite model

```bash
mkdir -p /home/pi/pet-elevator/camera_node/models
cd /tmp

wget https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
unzip coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip \
      detect.tflite labelmap.txt \
      -d /home/pi/pet-elevator/camera_node/models/
```

### 4. Configure the floor identity

```bash
sudo cp /home/pi/pet-elevator/deploy/elevator-camera.env /etc/default/elevator-camera
sudo nano /etc/default/elevator-camera
```

Edit the two values:

```
ELEVATOR_FLOOR=0            # 0 for ground floor, 1 for upper floor
ELEVATOR_BROKER=pet-elevator.local   # Pi 4B hostname or IP
```

### 5. Install the systemd service

```bash
sudo cp /home/pi/pet-elevator/deploy/elevator-camera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable elevator-camera
```

---

## First Run — Software Only (No 24V)

Before connecting the 24V motor supply, verify the software stack works.

### On the Pi 4

Start the controller (it will fail to connect to pigpiod on the motor pins, but
MQTT should start):

```bash
python -m controller.main
```

Expected output:
```
2024-...  controller.main          INFO     === Pet Elevator controller starting ===
2024-...  controller.mqtt_client   INFO     MQTT connected to localhost:1883
2024-...  controller.state_machine INFO     State: BOOT → HOMING
```

Homing will fail if the GPIO pins are not connected — that is expected at this
stage. Stop with Ctrl-C.

### On the Pi Zero 2 W (kart)

Test detection in isolation:

```bash
ELEVATOR_BROKER=pet-elevator.local python -m camera_node.main
```

Hold a dog toy or a printed dog photo in front of the camera. You should see log
lines like:

```
2024-...  camera_node.main   INFO  Dog detected — published score=0.847 to elevator/camera/kart/detection
```

On the Pi 4B, verify the MQTT event arrives:

```bash
mosquitto_sub -t 'elevator/#' -v
```

---

## Wiring Checks Before Powering the Motor

With the Pi 4 running and `pigpiod` started, check each safety input:

```bash
python3 -c "
import pigpio, time
pi = pigpio.pi()
pins = {17: 'LIMIT_BOTTOM', 22: 'ESTOP', 27: 'LIMIT_TOP'}
for p in pins:
    pi.set_mode(p, pigpio.INPUT)
    pi.set_pull_up_down(p, pigpio.PUD_UP)
for _ in range(10):
    for p, name in pins.items():
        print(f'{name}: {pi.read(p)}', end='   ')
    print()
    time.sleep(0.5)
pi.stop()
"
```

Expected readings:
- All switches in normal (untriggered) position: all pins read **0** (NC closed to GND)
- Trigger each switch manually: corresponding pin reads **1**
- Release: returns to **0**

If any pin reads **1** at rest, check the wiring for that switch.

---

## First Full Run (with 24V)

> Complete the wiring checks above before connecting the 24V PSU.

### 1. Start the controller service

```bash
sudo systemctl start elevator-controller
journalctl -u elevator-controller -f
```

### 2. Connect the 24V PSU

The controller will be mid-homing sequence. The platform should move slowly
**downward** until it hits the bottom limit switch, then stop. Log output:

```
INFO  Homing: moving DOWN to bottom limit switch
INFO  Homing complete — position = 0
INFO  State: HOMING → IDLE
```

**If the platform moves upward instead of downward:**
In `controller/config.py`, swap `DIR_UP` and `DIR_DOWN` (set `DIR_UP = 0`,
`DIR_DOWN = 1`), then restart the service.

**If the platform moves but does not stop:**
Check the bottom limit switch. With the switch released, GPIO 17 should read 0.
With the switch actuated, it should read 1. The carriage will stop at the top
limit switch as a safety fallback.

### 3. Open the web UI

On any phone or computer on the home network, open:

```
http://pet-elevator.local:8080
```

You should see:
- State badge showing **Ready** (green) after homing completes
- The dog emoji carriage at the bottom of the shaft
- **↑ Upper Floor** button enabled, **↓ Ground Floor** button disabled (already there)
- **Emergency Stop** button always visible
- A green **live** dot in the top-right corner confirming the SSE connection

The connection dot goes amber and shows **reconnecting…** if the network drops —
the page will reconnect automatically without a manual refresh.

> If `pet-elevator.local` does not resolve on your network, use the Pi 4B's IP
> address directly: `http://192.168.x.x:8080`. Find the IP with
> `hostname -I` on the Pi 4B.

### 4. Test floor control via the web UI

Press **↑ Upper Floor** in the browser. The carriage should animate upward as the
platform rises. The state badge changes to **Moving** (blue, pulsing) and back to
**Ready** on arrival.

Press **↓ Ground Floor** to return.

### 5. Send a manual floor command via MQTT (optional)

The web UI and MQTT commands are interchangeable — both publish to
`elevator/command`. From any machine on the home network:

```bash
mosquitto_pub -h pet-elevator.local -t elevator/command \
  -m '{"action": "go", "floor": 1}'
```

Check the retained status:

```bash
mosquitto_sub -h pet-elevator.local -t elevator/status -C 1
# → {"state": "idle", "floor": 1, "position": 413906}
```

### 6. Test the e-stop

While the platform is moving, either press the physical e-stop button **or** tap
**Emergency Stop** in the web UI. The platform must halt immediately and the state
badge must change to **Fault** (red, pulsing). The **Reset & Re-home** button
appears in the UI.

If using the physical e-stop, twist it to release before resetting. Then tap
**Reset & Re-home** in the UI (or send via MQTT):

```bash
mosquitto_pub -h pet-elevator.local -t elevator/command \
  -m '{"action": "reset"}'
```

The platform re-homes from wherever it stopped.

### 7. Start the camera services

On each landing Pi Zero 2 W:

```bash
sudo systemctl start elevator-camera
journalctl -u elevator-camera -f
```

Verify detections appear in the Pi 4B logs and that the elevator responds by
calling itself to the floor where the dog is waiting.

---

## Pi Zero 2 W Setup — Kart Sensor Node

### 1. Install dependencies

```bash
sudo apt update
sudo apt install -y python3-paho-mqtt python3-rpi.gpio
```

### 2. Clone / copy the project

```bash
git clone https://github.com/Thwart-Mallard/pet-elevator /home/pi/pet-elevator
```

### 3. Configure the broker address

```bash
sudo cp /home/pi/pet-elevator/deploy/elevator-kart.env /etc/default/elevator-kart
sudo nano /etc/default/elevator-kart
```

Set:

```
ELEVATOR_BROKER=pet-elevator.local   # Pi 4B hostname or IP
```

### 4. Install and enable the service

```bash
sudo cp /home/pi/pet-elevator/deploy/elevator-kart.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable elevator-kart
```

### 5. Test the sensors

Before fitting the kart, verify GPIO reads correctly:

```bash
ELEVATOR_BROKER=pet-elevator.local python -m kart_node.main
```

On the Pi 4B, watch the retained messages arrive:

```bash
mosquitto_sub -h pet-elevator.local -t 'elevator/kart/#' -v
```

Open and close the door — you should see:
```
elevator/kart/door {"status": "open"}
elevator/kart/door {"status": "closed"}
```

Place a weight on the pressure mat:
```
elevator/kart/pressure {"dog_present": true}
```

### 6. Start the kart service

```bash
sudo systemctl start elevator-kart
journalctl -u elevator-kart -f
```

---

## Adjusting Motion Parameters

All motion parameters are in `controller/config.py`. Restart the service after
any change.

| Want | Parameter | Edit |
|------|-----------|------|
| Lift faster | `MAX_SPEED_MM_S` | Increase (careful — test empty first) |
| Gentler start/stop | `ACCEL_MM_S2` | Decrease |
| Quieter homing | `HOMING_SPEED_MM_S` | Decrease |
| Elevator responds to lower-confidence detections | `DETECTION_CONFIDENCE_THRESHOLD` in `mqtt_client.py` | Decrease (min 0.50) |

At 25 mm/s, full travel (3048 mm) takes approximately **2 minutes 2 seconds**.

---

## Checking Logs

```bash
# Pi 4B controller
journalctl -u elevator-controller -f

# Pi Zero 2 W kart camera node
journalctl -u elevator-camera -f

# All MQTT traffic (from Pi 4B)
mosquitto_sub -t '#' -v
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Platform does not move | 24V PSU connected? DM542T power LED on? Check GPIO wiring |
| Platform moves wrong direction | Swap `DIR_UP`/`DIR_DOWN` in `config.py` or swap A+/A− on motor |
| Motor skips steps under load | Increase DM542T current (SW1–SW3). Verify 24V supply stable under load |
| Driver overheating | Reduce current setting. Add heatsink and 5V fan to DM542T |
| Homing overshoots, hits top limit | Bottom limit switch wiring — NC terminal must be tied to GND |
| State stuck in `fault` after reset | Check all NC switch pins — one may still read HIGH. Inspect wiring |
| Camera node not detecting dog | Check `journalctl -u elevator-camera`. Test model path. Hold dog image to camera |
| Detections not reaching Pi 4B | Ping `pet-elevator.local` from Zero 2 W. Check `ELEVATOR_BROKER` in `/etc/default/elevator-camera` |
| Elevator won't move — door blocked | Pi 4B received `kart_door: open`. Check door switch wiring on kart. Check `mosquitto_sub -t 'elevator/kart/door' -v` |
| Kart sensor not publishing | Check `journalctl -u elevator-kart` on kart Pi Zero. Verify `ELEVATOR_BROKER` in `/etc/default/elevator-kart` |
| Pressure mat not triggering | Check GPIO 27 wiring — one terminal to 3.3V, other to GPIO 27. Verify with `mosquitto_sub -t 'elevator/kart/pressure' -v` |
| `pigpio` connection refused | Run `sudo systemctl start pigpiod` on the Pi 4B |
| Missed steps at speed | 3.3V optocoupler current marginal — add level-shifter to 5V |
| Web UI not reachable | Is the service running? `sudo systemctl status elevator-controller`. Check port 8080 is not firewalled |
| `pet-elevator.local` not resolving | Use the Pi 4B IP address directly. mDNS can be unreliable on some routers |
| Web UI shows stale state / carriage stuck | SSE connection dropped — the dot turns amber. Refresh the page to force reconnect |
| Emergency Stop in UI does not respond | Check controller logs: `journalctl -u elevator-controller -f`. Verify MQTT is running on Pi 4B |
