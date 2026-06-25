# Hardware Reference

## Bill of Materials

### Pi 4 Controller Node

| Qty | Component                         | Notes                                              |
|-----|-----------------------------------|----------------------------------------------------|
| 1   | Raspberry Pi 4 (2 GB or above)    | Master controller, MQTT broker                     |
| 1   | 5V / 3A USB-C supply for Pi 4     | Separate from 24V motor supply                     |
| 1   | DM542T stepper driver             | 24–50V, up to 4.2A RMS, STEP/DIR interface         |
| 1   | NEMA 23 stepper motor, ≥ 3 N·m   | 1.8°/step, 200 steps/rev                           |
| 1   | 10:1 gearbox for NEMA 23          | Self-locking worm gear strongly recommended        |
| 1   | Winch drum, 75 mm diameter        | Cable must not cross-wind (single layer)           |
| 1   | 24V DC PSU, min 5A (120W)         | Switching supply preferred                         |
| 1   | 100 µF / 50V electrolytic cap     | Mandatory across DM542T V+/GND (back-EMF)          |
| 2   | Microswitch, NC, panel-mount      | Limit switches — one per floor                     |
| 1   | NC latching e-stop button         | Prominent red mushroom head, accessible to handler |
| —   | Wire, ferrule connectors          | Use ferrules on stepper motor wires                |

### Camera Nodes (×2, one per floor)

| Qty | Component                         | Notes                                              |
|-----|-----------------------------------|----------------------------------------------------|
| 2   | Raspberry Pi Zero 2 W             | One per landing                                    |
| 2   | Raspberry Pi Camera Module 3      | Standard CSI ribbon connector                      |
| 2   | 5V / 2.5A micro-USB supply        | One per Zero 2 W                                   |
| 2   | Camera enclosure / mount          | Weatherproof if near an exterior door              |

---

## Pi 4 GPIO Pin Assignment

All GPIO numbers are BCM (Broadcom) numbering, as used by `pigpio`.

### Safety Inputs (NC switches — INPUT with PUD_UP)

| BCM GPIO | Signal          | Switch wiring                          |
|----------|-----------------|----------------------------------------|
| GPIO 17  | LIMIT BOTTOM    | COM → GPIO 17, NC terminal → GND      |
| GPIO 22  | E-STOP          | COM → GPIO 22, NC terminal → GND      |
| GPIO 27  | LIMIT TOP       | COM → GPIO 27, NC terminal → GND      |

Pull-ups are enabled in software (`pigpio.PUD_UP`). When the NC switch is closed
(normal operation) the pin reads LOW. When the switch opens (at limit or wire break)
the pin reads HIGH — both conditions trigger an immediate stop.

### Stepper Driver Outputs

| BCM GPIO | Signal       | DM542T pin | Notes                                   |
|----------|--------------|------------|-----------------------------------------|
| GPIO 18  | STEP (PUL+)  | PUL+       | Common-cathode: GPIO drives + side       |
| GPIO 23  | DIR          | DIR+       | Common-cathode: GPIO drives + side       |
| GPIO 24  | ENA          | ENA+       | LOW = motor enabled, HIGH = disabled     |
| GND      | Signal GND   | PUL−, DIR−, ENA− | All minus-sides tied to Pi GND  |

**Common-cathode wiring note:** DM542T PUL−, DIR−, ENA− are all tied to GND.
Pi GPIO drives the + sides at 3.3V. The optocoupler current is ≈ 9.5 mA
((3.3 − 1.2) / 220Ω internal resistor). The DM542T specification minimum is 10 mA.
This works on every DM542T tested, but if missed steps occur under load add a
BSS138-based level-shifter board to bring GPIO signals to 5V.

---

## DM542T Configuration

### Current Setting (SW1–SW3)

Set to match your motor's rated phase current. The table below is for the
common DM542T variant — consult your unit's datasheet if values differ.

| SW1 | SW2 | SW3 | Peak current | RMS current |
|-----|-----|-----|--------------|-------------|
| ON  | ON  | ON  | 1.00 A       | 0.71 A      |
| OFF | ON  | ON  | 1.46 A       | 1.04 A      |
| ON  | OFF | ON  | 1.91 A       | 1.35 A      |
| OFF | OFF | ON  | 2.37 A       | 1.68 A      |
| ON  | ON  | OFF | 2.84 A       | 2.01 A      |
| OFF | ON  | OFF | 3.31 A       | 2.34 A      |
| ON  | OFF | OFF | 3.76 A       | 2.66 A      |
| OFF | OFF | OFF | 4.20 A       | 2.97 A      |

Start conservatively (≈ 70% of rated current). Increase only if the motor skips
steps under load. The driver will run warm — add a small heatsink if ambient
temperature is high.

**SW4 — Standstill current reduction:** ON = half current when stationary.
For a loaded cable-winch, set SW4 OFF (full current at standstill) to
maintain holding torque. The software never de-energises the motor.

### Microstep Setting (SW5–SW8)

The firmware is calibrated for **1/16 microstep → 3200 pulses/rev**.

```
Steps/mm = (200 × 16 × 10) / (π × 75) = 32,000 / 235.62 = 135.81 steps/mm
```

| SW5 | SW6 | SW7 | SW8 | Pulses/rev | Microstep |
|-----|-----|-----|-----|------------|-----------|
| ON  | ON  | OFF | OFF | 400        | 1/2       |
| OFF | ON  | OFF | OFF | 800        | 1/4       |
| ON  | OFF | OFF | OFF | 1600       | 1/8       |
| OFF | OFF | OFF | OFF | 3200       | **1/16** ← use this |
| ON  | ON  | ON  | OFF | 6400       | 1/32      |
| OFF | ON  | ON  | OFF | 12800      | 1/64      |

If your DM542T has a different switch layout, confirm by checking the label on the
driver case or the datasheet for your specific batch.

---

## Motor Coil Connections

| DM542T pin | NEMA 23 wire | Notes                             |
|------------|--------------|-----------------------------------|
| A+         | Coil 1 +     | Find pairs with multimeter:       |
| A−         | Coil 1 −     | resistance ≈ 2Ω within a pair,    |
| B+         | Coil 2 +     | open-circuit between pairs        |
| B−         | Coil 2 −     |                                   |

If the platform moves in the wrong direction on first power-on, swap A+ and A−
(or B+ and B−). The direction can also be inverted in software by changing
`DIR_UP` / `DIR_DOWN` in `controller/config.py`.

---

## Mechanical Safety Notes

1. **Gearbox self-locking:** A worm-gear gearbox holds the load passively when the
   motor is de-energised. A helical gearbox will not — the load can back-drive and
   drop the platform. Confirm your gearbox type before any load testing.

2. **Cable termination:** Use a swaged or crimped cable end, not a knot.
   Inspect the cable at every 50 cycles for the first 500 cycles, then monthly.

3. **Drum winding:** The cable must not cross-wind or stack. Use a level-wind
   mechanism, or ensure the drum is wide enough for a single layer across the full
   3048 mm travel. Single-layer diameter change on a 75 mm drum with 3 mm cable
   is ≈ 4% — within the calibration tolerance.

4. **Platform gates:** Physical barriers at each landing prevent the dog stepping
   onto a moving platform. Consider wiring gate interlocks in series with the
   e-stop circuit.

5. **Counterweight:** A counterweight equal to ~60% of the platform weight reduces
   the effective cable tension, improves the safety margin, and cuts motor current
   draw significantly. Strongly recommended.
