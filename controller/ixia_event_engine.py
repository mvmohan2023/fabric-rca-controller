import argparse
import json
import subprocess
import time
from typing import Any, Dict

from controller.ixia_client import IxiaClient


class EventEngine:
    def __init__(self, api_server: str, inventory_path: str) -> None:
        self.client = IxiaClient(api_server=api_server, inventory_path=inventory_path)

    def traffic_start(self) -> None:
        print("Starting traffic")
        result = self.client.traffic_start()
        state = result.get("state")
        text = (result.get("result") or "").strip()

        if state == "SUCCESS":
            print("Traffic started successfully")
            return

        if "kStarted" in text or "Traffic Module in State : kStarted" in text:
            print("Traffic already running")
            return

        raise RuntimeError(f"traffic_start failed: {result}")

    def traffic_stop(self) -> None:
        print("Stopping traffic")
        result = self.client.traffic_stop()
        state = result.get("state")
        text = (result.get("result") or "").strip()

        if state == "SUCCESS":
            print("Traffic stopped successfully")
            return

        if "kStopped" in text or "already stopped" in text.lower() or "not running" in text.lower():
            print("Traffic already stopped")
            return

        raise RuntimeError(f"traffic_stop failed: {result}")

    def traffic_apply(self) -> None:
        print("Applying traffic")
        result = self.client.traffic_apply()
        state = result.get("state")
        text = (result.get("result") or "").strip()

        if state == "SUCCESS":
            print("Traffic apply successful")
            return

        # IxNetwork often rejects apply if traffic is already active / config state is not editable.
        if "Traffic Apply" in text or "L2/L3 Traffic Apply" in text:
            print(f"Traffic apply warning: {text}")
            return

        raise RuntimeError(f"traffic_apply failed: {result}")

    def scale_toggle(
        self,
        topology: str,
        network_group: str,
        low: int,
        high: int,
        cycles: int,
        settle: int,
    ) -> None:
        print(
            f"Running scale toggle: topology={topology}, "
            f"network_group={network_group}, low={low}, high={high}, "
            f"cycles={cycles}, settle={settle}"
        )

        cmd = (
            f"python -m controller.ixia_client scale-toggle "
            f"--topology {json.dumps(topology)} "
            f"--network-group {json.dumps(network_group)} "
            f"--low {int(low)} "
            f"--high {int(high)} "
            f"--cycles {int(cycles)} "
            f"--settle {int(settle)}"
        )

        rc = subprocess.call(cmd, shell=True)
        if rc != 0:
            raise RuntimeError(f"scale_toggle failed rc={rc}")

    def link_flap(self, device: str, interface: str, duration: int) -> None:
        print(f"Flapping link: device={device}, interface={interface}, duration={duration}s")

        disable_cmd = (
            f"ssh root@{device} "
            f"'cli -c \"configure; set interfaces {interface} disable; commit and-quit\"'"
        )
        enable_cmd = (
            f"ssh root@{device} "
            f"'cli -c \"configure; delete interfaces {interface} disable; commit and-quit\"'"
        )

        rc = subprocess.call(disable_cmd, shell=True)
        if rc != 0:
            raise RuntimeError(f"link_flap disable failed rc={rc}")

        time.sleep(int(duration))

        rc = subprocess.call(enable_cmd, shell=True)
        if rc != 0:
            raise RuntimeError(f"link_flap enable failed rc={rc}")


def load_catalog(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def run_events(engine: EventEngine, catalog: Dict[str, Any]) -> None:
    events = catalog.get("events", [])
    for event in events:
        name = event.get("name", "unnamed")
        action = event.get("action")
        settle = int(event.get("settle", 5))

        print(f"\nEVENT: {name}")

        if action == "traffic_start":
            engine.traffic_start()

        elif action == "traffic_stop":
            engine.traffic_stop()

        elif action == "traffic_apply":
            return 1
            engine.traffic_apply()

        elif action == "network_group_scale_toggle":
            engine.scale_toggle(
                topology=event["topology"],
                network_group=event["network_group"],
                low=event["low"],
                high=event["high"],
                cycles=event.get("cycles", 1),
                settle=event.get("settle", 30),
            )

        elif action == "link_flap":
            engine.link_flap(
                device=event["device"],
                interface=event["interface"],
                duration=event.get("duration", 5),
            )

        else:
            raise RuntimeError(f"Unsupported action in catalog: {action}")

        print(f"Settling for {settle}s")
        time.sleep(settle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run IXIA / fabric event catalog")
    parser.add_argument("--api-server", required=True)
    parser.add_argument("--inventory", default="controller/ixia_inventory.json")
    parser.add_argument("--catalog", default="controller/event_catalog.json")
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    engine = EventEngine(api_server=args.api_server, inventory_path=args.inventory)
    run_events(engine, catalog)


if __name__ == "__main__":
    main()
