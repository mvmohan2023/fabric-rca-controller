from pathlib import Path
from typing import Any, Dict
import yaml


class InventoryError(Exception):
    pass


def load_inventory(path: str = "inventory/inventory.yaml") -> Dict[str, Any]:
    inv_path = Path(path)
    if not inv_path.exists():
        raise InventoryError(f"Inventory file not found: {inv_path}")

    with inv_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise InventoryError("Inventory YAML is not a dictionary")

    if "nodes" not in data or not isinstance(data["nodes"], dict):
        raise InventoryError("Inventory must contain a 'nodes' dictionary")

    return data


def get_nodes(path: str = "inventory/inventory.yaml") -> Dict[str, Any]:
    return load_inventory(path)["nodes"]


if __name__ == "__main__":
    inventory = load_inventory()
    print("Inventory loaded successfully")
    print(f"Total nodes: {len(inventory['nodes'])}")
    for name, node in inventory["nodes"].items():
        print(
            f"{name}: hostname={node['hostname']}, "
            f"mgmt_ip={node['mgmt_ip']}, role={node['role']}, "
            f"platform={node['platform']}"
        )
