import threading
import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)


class State(Enum):
    BOOT   = auto()
    HOMING = auto()
    IDLE   = auto()
    MOVING = auto()
    FAULT  = auto()


class ElevatorFSM:
    """
    Elevator state machine.

    Thread model:
      - Motor moves run in a daemon thread spawned by cmd_go / cmd_home.
      - Safety callbacks arrive on the pigpio callback thread.
      - MQTT commands arrive on the paho network thread.
      All three paths use self._lock (RLock) when touching self.state /
      self.current_floor.  on_status_change is called *outside* the lock to
      avoid holding it across a network publish.
    """

    def __init__(self, motor, safety=None, on_status_change=None) -> None:
        self.motor = motor
        self.safety = safety                        # set before start() is called
        self.on_status_change = on_status_change    # callable(status_dict) or None
        self.state = State.BOOT
        self.current_floor: int | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Home the carriage on boot.  Blocks until homing completes."""
        self._set_state(State.HOMING)
        self._do_home_sync()

    # ------------------------------------------------------------------ #
    # External commands (safe to call from any thread)                    #
    # ------------------------------------------------------------------ #

    def cmd_go(self, floor: int) -> None:
        with self._lock:
            if self.state != State.IDLE:
                logger.info("cmd_go(%d) ignored — state is %s", floor, self.state.name)
                return
            if floor == self.current_floor:
                logger.info("cmd_go(%d): already at floor", floor)
                return
            self._set_state(State.MOVING)

        threading.Thread(target=self._do_move, args=(floor,), daemon=True).start()

    def cmd_home(self) -> None:
        with self._lock:
            if self.state not in (State.IDLE, State.FAULT):
                logger.info("cmd_home ignored — state is %s", self.state.name)
                return
            self._set_state(State.HOMING)

        threading.Thread(target=self._do_home_sync, daemon=True).start()

    def cmd_reset(self) -> None:
        """Re-home after a fault is acknowledged."""
        self.cmd_home()

    def on_safety_fault(self, pin_name: str) -> None:
        """Called from the pigpio callback thread on any NC switch opening."""
        self.motor.request_stop()
        self._set_state(State.FAULT)
        logger.error("Safety fault: %s — elevator stopped", pin_name)

    @property
    def status(self) -> dict:
        return self._build_status()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _do_move(self, floor: int) -> None:
        success = self.motor.move_to_floor(floor)
        with self._lock:
            if self.state == State.FAULT:
                return  # safety fault fired during the move; fault state already set
            if success:
                self.current_floor = floor
                self._set_state(State.IDLE)
            else:
                self._set_state(State.FAULT)

    def _do_home_sync(self) -> None:
        success = self.motor.home(safety_monitor=self.safety)
        with self._lock:
            if success:
                if self.safety:
                    self.safety.enable_bottom_limit()
                self.current_floor = 0
                self._set_state(State.IDLE)
            else:
                self._set_state(State.FAULT)

    def _set_state(self, new_state: State) -> None:
        """Transition to new_state and notify.  Acquires _lock internally."""
        with self._lock:
            old = self.state
            self.state = new_state
            status = self._build_status()

        logger.info("State: %s → %s", old.name, new_state.name)
        if self.on_status_change:
            try:
                self.on_status_change(status)
            except Exception:
                logger.exception("on_status_change raised")

    def _build_status(self) -> dict:
        return {
            "state":    self.state.name.lower(),
            "floor":    self.current_floor,
            "position": self.motor.current_position,
        }
