"""
Pet Elevator — Pi 4 master controller entry point.

Prerequisites on the Pi 4:
  sudo apt install pigpio python3-pigpio python3-paho-mqtt
  sudo systemctl enable pigpiod
  sudo systemctl start pigpiod
  pip install paho-mqtt flask

Web UI:  http://pet-elevator.local:8080

Run:
  python -m controller.main
"""

import logging
import signal
import sys
import pigpio

from .motor         import StepperMotor
from .safety        import SafetyMonitor
from .state_machine import ElevatorFSM
from .mqtt_client   import MQTTClient
from .web_ui        import WebUI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    # Connect to pigpio daemon
    pi = pigpio.pi()
    if not pi.connected:
        logger.critical(
            "Cannot connect to pigpio daemon.  Run: sudo systemctl start pigpiod"
        )
        sys.exit(1)

    motor  = StepperMotor(pi)
    fsm    = ElevatorFSM(motor)

    # SafetyMonitor needs fsm.on_safety_fault; FSM needs safety.enable_bottom_limit().
    # Wire them together before start() is called.
    safety = SafetyMonitor(pi, fault_callback=fsm.on_safety_fault)
    fsm.safety = safety

    # MQTTClient publishes status; FSM calls on_status_change on every transition.
    mqtt_client = MQTTClient(fsm)
    fsm.on_status_change = mqtt_client.publish_status

    mqtt_client.start()
    logger.info("MQTT client started")

    web_ui = WebUI()
    web_ui.start()

    def shutdown(sig, frame) -> None:
        logger.info("Shutting down (signal %d)", sig)
        motor.request_stop()
        safety.cancel()
        mqtt_client.stop()
        web_ui.stop()
        motor.disable()
        pi.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("=== Pet Elevator controller starting ===")
    fsm.start()                # blocks until homing completes, then returns

    if fsm.state.name == "FAULT":
        logger.error("Homing failed — elevator in FAULT state.  Fix and send 'reset' command.")

    signal.pause()             # sleep until SIGINT / SIGTERM


if __name__ == "__main__":
    main()
