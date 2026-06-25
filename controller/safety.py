import logging
import pigpio

from . import config

logger = logging.getLogger(__name__)

_PIN_NAMES = {
    config.LIMIT_BOTTOM_PIN: "bottom_limit",
    config.LIMIT_TOP_PIN:    "top_limit",
    config.ESTOP_PIN:        "estop",
}


class SafetyMonitor:
    """
    Monitors NC limit switches and the e-stop button via pigpio edge callbacks.
    All pins are pulled HIGH internally; a RISING_EDGE means the NC circuit opened
    (switch at limit, or wire fault) — both conditions require an immediate stop.

    Bottom-limit faults can be suppressed during homing so the motor's polling
    loop can claim the event without racing with this callback.
    """

    def __init__(self, pi: pigpio.pi, fault_callback) -> None:
        """
        fault_callback(pin_name: str) is called from the pigpio callback thread
        on any safety fault.  It must be thread-safe (typically just sets a flag
        and calls motor.request_stop()).
        """
        self.pi = pi
        self.fault_callback = fault_callback
        self.suppress_bottom_limit = False  # set True during homing
        self._callbacks: list = []

        # Setup top limit and e-stop immediately
        for pin in (config.LIMIT_TOP_PIN, config.ESTOP_PIN):
            pi.set_mode(pin, pigpio.INPUT)
            pi.set_pull_up_down(pin, pigpio.PUD_UP)
            cb = pi.callback(pin, pigpio.RISING_EDGE, self._on_fault)
            self._callbacks.append(cb)

        # Bottom limit: configure pin now, enable callback after homing
        pi.set_mode(config.LIMIT_BOTTOM_PIN, pigpio.INPUT)
        pi.set_pull_up_down(config.LIMIT_BOTTOM_PIN, pigpio.PUD_UP)
        self._bottom_cb = None

        logger.info("SafetyMonitor ready (bottom-limit callback deferred until homed)")

    def enable_bottom_limit(self) -> None:
        """Register the bottom-limit fault callback. Call once after homing."""
        if self._bottom_cb is None:
            self._bottom_cb = self.pi.callback(
                config.LIMIT_BOTTOM_PIN, pigpio.RISING_EDGE, self._on_fault
            )
            logger.info("Bottom-limit fault detection enabled")

    def read_all(self) -> dict[str, int]:
        """Snapshot of all safety inputs (0 = OK, 1 = fault / wire break)."""
        return {name: self.pi.read(pin) for pin, name in _PIN_NAMES.items()}

    def any_fault(self) -> bool:
        return any(self.read_all().values())

    def cancel(self) -> None:
        """Deregister all callbacks — call on shutdown."""
        for cb in self._callbacks:
            cb.cancel()
        if self._bottom_cb:
            self._bottom_cb.cancel()
        self._callbacks.clear()
        self._bottom_cb = None

    # ------------------------------------------------------------------ #

    def _on_fault(self, gpio: int, level: int, tick: int) -> None:
        if gpio == config.LIMIT_BOTTOM_PIN and self.suppress_bottom_limit:
            return
        name = _PIN_NAMES.get(gpio, f"gpio_{gpio}")
        logger.warning("Safety fault: %s (gpio=%d)", name, gpio)
        self.fault_callback(name)
