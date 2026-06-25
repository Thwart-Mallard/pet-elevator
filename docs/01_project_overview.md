# Pet Elevator — Project Overview

## Purpose

A two-floor vertical cable-winch lift for an ageing dog with mobility difficulties.
The lift carries the dog between a ground floor and a main floor. It can be called
automatically when the dog is detected waiting at a landing, or commanded manually
via MQTT from any device on the home network.

---

## Scope

### What is built

- Vertical cable-winch lift driven by a NEMA 23 stepper motor and 10:1 gearbox
- Raspberry Pi 4 as the master controller — runs the state machine, motor control,
  safety monitoring, and an MQTT broker
- Two Pi Zero 2 W camera nodes, one at each floor landing — run on-device TFLite
  dog detection and publish detections over WiFi to the Pi 4
- Full safety system: two NC limit switches, NC latching e-stop, homing on boot
- systemd services so everything starts automatically on power-on

### How it works

1. On boot the Pi 4 homes the carriage to the ground floor limit switch.
2. Camera nodes watch their respective landings continuously.
3. When a node detects the dog with ≥ 80% confidence it publishes a detection event
   to the MQTT broker on the Pi 4.
4. The Pi 4 state machine calls the elevator to that floor.
5. Manual floor commands can also be sent via MQTT from any home-network device.

---

## Design Decisions and Rationale

### Why Raspberry Pi 4 (not ESP32)?

The Pi 4 runs a real Linux OS, which gives:
- Python with the `pigpio` library for hardware-accurate DMA step timing
- Mosquitto MQTT broker running locally — no external broker dependency
- systemd for reliable auto-start and logging
- Easy SSH access for debugging and updates

The ESP32 prototyped the V1 concept; the Pi 4 is the production platform.

### Why Pi Zero 2 W for camera nodes?

The Zero 2 W has a quad-core ARM Cortex-A53, enough to run TFLite MobileNet SSD
inference at ~1 fps without sending video off-device. This keeps:
- Latency low (no round-trip to a cloud API)
- Privacy preserved (no video leaves the home network)
- Reliability high (no cloud dependency for safety-adjacent function)

### Why NEMA 23 with 75 mm drum?

The original 250 mm drum was unsafe at any practical torque:

```
Load (15 kg dog + ~10 kg platform) ≈ 245 N at cable

NEMA 23 (3 N·m) × 10:1 gearbox × 0.85 efficiency = 25.5 N·m
Force at 37.5 mm drum radius = 340 N  →  1.4× margin over 245 N ✓

Original 250 mm drum:
Force at 125 mm radius = 204 N  →  4× too low, unsafe ✗
```

A minimum 1.5× safety factor is recommended; adding a counterweight improves this
further without increasing motor current.

### Why NC (Normally Closed) safety switches?

All safety inputs are wired Normally Closed to GND. The Pi GPIO reads LOW during
normal operation and HIGH when the switch opens — whether intentionally triggered
or due to a broken wire. Both conditions halt the motor. This is standard
industrial safe-fail practice.

### Why keep the motor energised when stopped?

Stepper motors hold position only while energised. A cable-winch under gravity load
will back-drive if the motor is de-energised, dropping the platform. `ENA` is held
active (motor enabled) at all times. De-energising is only done during maintenance
via an explicit `motor.disable()` call.

A self-locking worm-gear gearbox provides additional passive mechanical hold.

### Why DMA waveforms for stepping (not software PWM)?

The `pigpio` daemon generates step pulses using the Pi's DMA controller, completely
independent of the Python process and the OS scheduler. This gives hardware-accurate
step timing (±1 µs) at 3400+ steps/second without burning a CPU core. Python's GIL
is irrelevant.

---

## Physical Specification

| Parameter           | Value                           |
|---------------------|---------------------------------|
| Floor separation    | 3048 mm (10 ft)                 |
| Max load            | 15 kg dog + ~10 kg platform     |
| Drum diameter       | 75 mm                           |
| Gearbox ratio       | 10:1 (worm gear, self-locking)  |
| Microstep setting   | 1/16                            |
| Steps per mm        | 135.81                          |
| Total steps (full)  | ~413,900                        |
| Lift speed          | 25 mm/s (~2 min full travel)    |
| Homing speed        | 5 mm/s                          |
| Acceleration        | 8 mm/s² (gentle for dog comfort)|
| Motor supply        | 24 V DC, min 5 A (120 W)        |
| Logic supply        | 5 V / 3 A USB-C (Pi 4)          |

---

## Project File Tree

```
Project_Pet_Elevator/
├── docs/
│   ├── 01_project_overview.md       ← this file
│   ├── 02_hardware.md               ← BOM, GPIO pins, DM542T setup, wiring
│   ├── 03_software_architecture.md  ← module map, state machine, MQTT API
│   └── 04_getting_started.md        ← installation and first-run guide
│
├── controller/                      ← Pi 4 master controller (Python)
│   ├── config.py                    ← all pins, speeds, MQTT settings
│   ├── motor.py                     ← DMA stepper control (pigpio waves)
│   ├── safety.py                    ← NC switch monitoring (pigpio callbacks)
│   ├── state_machine.py             ← elevator FSM
│   ├── mqtt_client.py               ← paho-mqtt wrapper
│   ├── web_ui.py                    ← Flask web UI (port 8080, SSE)
│   ├── templates/
│   │   └── index.html               ← mobile-friendly control interface
│   └── main.py                      ← entry point
│
├── camera_node/                     ← Pi Zero 2 W camera node (Python)
│   ├── config.py                    ← floor identity, MQTT, model paths
│   ├── detector.py                  ← TFLite MobileNet SSD wrapper
│   └── main.py                      ← capture → infer → publish loop
│
├── deploy/
│   ├── elevator-controller.service  ← systemd unit for Pi 4
│   ├── elevator-camera.service      ← systemd unit for Pi Zero 2 W
│   └── elevator-camera.env          ← environment template for camera nodes
│
├── firmware/                        ← original ESP32 prototype (reference only)
│
└── wiring/
    └── wiring_diagram.svg           ← open in any browser
```
