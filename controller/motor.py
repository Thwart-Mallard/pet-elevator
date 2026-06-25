import math
import time
import threading
import logging
import pigpio

from . import config

logger = logging.getLogger(__name__)

# pigpio wave_chain loop tokens
_LOOP_START = 255
_LOOP_END   = 255
_LOOP_END_2 = 1
_MAX_LOOP_COUNT = 65535          # 16-bit loop counter in wave_chain
_MAX_PULSES_PER_WAVE = 10_000   # conservative — pigpio default limit is 12 000


class StepperMotor:
    """
    Controls a NEMA 23 stepper via DM542T using pigpio DMA waveforms.
    Trapezoidal velocity profile: accel → cruise (loop) → decel.
    Thread-safe: only one move executes at a time (enforced by _lock).
    """

    def __init__(self, pi: pigpio.pi) -> None:
        self.pi = pi
        self.current_position: int | None = None  # steps from home; None until homed
        self._stop_requested = False
        self._lock = threading.Lock()

        for pin in (config.STEP_PIN, config.DIR_PIN, config.ENABLE_PIN):
            pi.set_mode(pin, pigpio.OUTPUT)
        pi.write(config.STEP_PIN, 0)
        pi.write(config.DIR_PIN, 0)
        self.enable()
        logger.info("StepperMotor ready")

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def enable(self) -> None:
        """Apply holding torque (ENA+ LOW in common-cathode wiring)."""
        self.pi.write(config.ENABLE_PIN, 0)

    def disable(self) -> None:
        """Release torque — maintenance only."""
        self.pi.write(config.ENABLE_PIN, 1)

    def request_stop(self) -> None:
        """Signal the running move to abort and stop the DMA wave immediately."""
        self._stop_requested = True
        self.pi.wave_tx_stop()

    def home(self, safety_monitor=None) -> bool:
        """
        Crawl DOWN until the bottom NC switch opens (pin goes HIGH), then set
        current_position to 0.  Suppresses bottom-limit fault callbacks for the
        duration so SafetyMonitor does not race with the homing poll.
        """
        with self._lock:
            logger.info("Homing: moving DOWN to bottom limit switch")
            self._stop_requested = False

            if safety_monitor:
                safety_monitor.suppress_bottom_limit = True

            try:
                # Check if already at home
                if self.pi.read(config.LIMIT_BOTTOM_PIN) == 1:
                    logger.info("Homing: already at bottom limit")
                    self.current_position = 0
                    return True

                self.pi.write(config.DIR_PIN, config.DIR_DOWN)
                time.sleep(0.001)

                interval_s = 1.0 / config.HOMING_STEPS_S

                while True:
                    if self._stop_requested:
                        logger.warning("Homing aborted by stop request")
                        return False

                    if self.pi.read(config.LIMIT_BOTTOM_PIN) == 1:
                        break

                    self.pi.write(config.STEP_PIN, 1)
                    time.sleep(5e-6)
                    self.pi.write(config.STEP_PIN, 0)
                    time.sleep(interval_s - 5e-6)

                self.current_position = 0
                logger.info("Homing complete — position = 0")
                return True

            finally:
                if safety_monitor:
                    safety_monitor.suppress_bottom_limit = False

    def move_to_floor(self, floor: int) -> bool:
        """Move carriage to the specified floor (0 = ground, 1 = upper)."""
        if self.current_position is None:
            logger.error("move_to_floor: not homed")
            return False

        if floor not in config.FLOOR_POSITIONS:
            logger.error("move_to_floor: unknown floor %d", floor)
            return False

        delta = config.FLOOR_POSITIONS[floor] - self.current_position
        if delta == 0:
            logger.info("move_to_floor: already at floor %d", floor)
            return True

        direction = config.DIR_UP if delta > 0 else config.DIR_DOWN
        logger.info("Moving to floor %d (%d steps %s)", floor, abs(delta),
                    "UP" if direction == config.DIR_UP else "DOWN")
        return self._execute_move(abs(delta), direction)

    # ------------------------------------------------------------------ #
    # Internal wave-based motion                                           #
    # ------------------------------------------------------------------ #

    def _execute_move(self, num_steps: int, direction: int) -> bool:
        with self._lock:
            self._stop_requested = False
            waves_to_delete: list[int] = []

            try:
                accel_steps, decel_steps, cruise_steps, v_peak = \
                    self._compute_profile(num_steps)

                self.pi.write(config.DIR_PIN, direction)
                time.sleep(0.001)

                chain: list[int] = []

                # — Acceleration —
                for wid in self._build_variable_waves(accel_steps, v_peak, accel=True):
                    waves_to_delete.append(wid)
                    chain.append(wid)

                # — Cruise (single-step wave, repeated via wave_chain loops) —
                if cruise_steps > 0:
                    cruise_wid = self._build_cruise_wave(v_peak)
                    waves_to_delete.append(cruise_wid)
                    remaining = cruise_steps
                    while remaining > 0:
                        count = min(remaining, _MAX_LOOP_COUNT)
                        lo, hi = count & 0xFF, (count >> 8) & 0xFF
                        chain += [_LOOP_START, 0, cruise_wid, _LOOP_END, _LOOP_END_2, lo, hi]
                        remaining -= count

                # — Deceleration —
                for wid in self._build_variable_waves(decel_steps, v_peak, accel=False):
                    waves_to_delete.append(wid)
                    chain.append(wid)

                if not chain:
                    return True

                self.pi.wave_chain(chain)

                while self.pi.wave_tx_busy():
                    if self._stop_requested:
                        self.pi.wave_tx_stop()
                        logger.warning("Move aborted mid-wave")
                        return False
                    time.sleep(0.05)

                # Commit position only on clean completion
                if direction == config.DIR_UP:
                    self.current_position += num_steps
                else:
                    self.current_position -= num_steps
                self.current_position = max(0, min(self.current_position, config.TOTAL_STEPS))

                logger.info("Move complete — position: %d steps", self.current_position)
                return True

            except Exception:
                logger.exception("_execute_move failed")
                self.pi.wave_tx_stop()
                return False

            finally:
                for wid in waves_to_delete:
                    try:
                        self.pi.wave_delete(wid)
                    except Exception:
                        pass

    def _compute_profile(self, num_steps: int):
        """Return (accel_steps, decel_steps, cruise_steps, v_peak)."""
        full_accel = int(config.MAX_SPEED_STEPS_S ** 2 / (2 * config.ACCEL_STEPS_S2))
        accel_steps = min(full_accel, num_steps // 2)
        decel_steps = accel_steps
        cruise_steps = num_steps - accel_steps - decel_steps

        if accel_steps < full_accel:
            # Short move — triangular profile, v_peak below maximum
            v_peak = math.sqrt(2 * config.ACCEL_STEPS_S2 * accel_steps) if accel_steps else 1.0
        else:
            v_peak = config.MAX_SPEED_STEPS_S

        return accel_steps, decel_steps, cruise_steps, v_peak

    def _build_variable_waves(self, num_steps: int, v_peak: float,
                               accel: bool) -> list[int]:
        """
        Build one or more waves for the accel or decel ramp.
        Splits into chunks ≤ _MAX_PULSES_PER_WAVE pulses to stay within pigpio limits.
        Returns list of wave IDs.
        """
        if num_steps == 0:
            return []

        step_bit = 1 << config.STEP_PIN
        wave_ids = []
        pulses: list[pigpio.pulse] = []

        for i in range(num_steps):
            # Step index from the start (accel) or from the end (decel) for velocity calc
            idx = i + 1 if accel else (num_steps - i)
            v = min(math.sqrt(2 * config.ACCEL_STEPS_S2 * idx), v_peak)
            v = max(v, 50)                          # floor at 50 steps/s to avoid ÷0
            interval_us = int(1_000_000 / v)

            pulses.append(pigpio.pulse(step_bit, 0, 5))
            pulses.append(pigpio.pulse(0, step_bit, max(1, interval_us - 5)))

            if len(pulses) >= _MAX_PULSES_PER_WAVE:
                self.pi.wave_add_generic(pulses)
                wave_ids.append(self.pi.wave_create())
                pulses = []

        if pulses:
            self.pi.wave_add_generic(pulses)
            wave_ids.append(self.pi.wave_create())

        return wave_ids

    def _build_cruise_wave(self, v_peak: float) -> int:
        """Single-step wave at cruise speed, repeated by wave_chain loop."""
        step_bit = 1 << config.STEP_PIN
        interval_us = int(1_000_000 / v_peak)
        self.pi.wave_add_generic([
            pigpio.pulse(step_bit, 0, 5),
            pigpio.pulse(0, step_bit, max(1, interval_us - 5)),
        ])
        return self.pi.wave_create()
