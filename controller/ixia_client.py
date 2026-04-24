# controller/ixia_client.py

import argparse
import json
import os
import shlex
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple
import time
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


DEFAULT_IXIA_INVENTORY = os.path.join(os.path.dirname(__file__), "ixia_inventory.json")
DEFAULT_TIMEOUT = 30


class IxiaClientError(Exception):
    pass


def load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


class IxiaClient:
    def __init__(
        self,
        api_server: str,
        inventory_path: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        verify_tls: bool = False,
    ) -> None:
        self.api_server = api_server
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.base_url = f"https://{api_server}:11009/api/v1"
        self.session = requests.Session()
        self.session.verify = verify_tls
        self.session.headers.update({"Content-Type": "application/json"})

        self.inventory_path = inventory_path or DEFAULT_IXIA_INVENTORY
        self.inventory = load_json_file(self.inventory_path) if os.path.exists(self.inventory_path) else {}
        self.helper_host = self.inventory.get("api_helper_host", {})
        self.session_id: Optional[int] = None

    # ------------------------------------------------------------
    # Generic REST helpers
    # ------------------------------------------------------------
    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = self._url(path)
        response = self.session.post(url, json=payload, timeout=self.timeout, verify=self.verify_tls)
        if response.status_code not in (200, 201, 202):
            raise IxiaClientError(
                f"POST {url} failed: status={response.status_code}, body={response.text}"
            )
        if not response.text.strip():
            return {}
        return response.json()

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path

        if self.base_url.endswith("/api/v1") and path.startswith("/api/v1/"):
            path = path[len("/api/v1"):]

        return f"{self.base_url}{path}" 
    def traffic_apply(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        sid = self.resolve_session_id(session_id)
        return self._post_json(f"/sessions/{sid}/ixnetwork/traffic/operations/apply", {
            "arg1": f"/api/v1/sessions/{sid}/ixnetwork/traffic"
        })

    def traffic_start(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        sid = self.resolve_session_id(session_id)
        return self._post_json(f"/sessions/{sid}/ixnetwork/traffic/operations/start", {
            "arg1": f"/api/v1/sessions/{sid}/ixnetwork/traffic"
        })

    def traffic_stop(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        sid = self.resolve_session_id(session_id)
        return self._post_json(f"/sessions/{sid}/ixnetwork/traffic/operations/stop", {
            "arg1": f"/api/v1/sessions/{sid}/ixnetwork/traffic"
        })

    def traffic_generate(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        sid = self.resolve_session_id(session_id)
        return self._post_json(f"/sessions/{sid}/ixnetwork/traffic/operations/generate", {
            "arg1": f"/api/v1/sessions/{sid}/ixnetwork/traffic"
        })
    
    def _normalize_path(self, path: str) -> str:
        """
        Handles:
        - full URLs
        - hrefs like /api/v1/sessions/1/ixnetwork/...
        - relative paths like /sessions/1/ixnetwork/...
        """
        if path.startswith("http://") or path.startswith("https://"):
            return path

        if path.startswith("/api/v1/"):
            return f"https://{self.api_server}:11009{path}"

        if not path.startswith("/"):
            path = "/" + path

        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        expected: Tuple[int, ...] = (200,),
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = self._normalize_path(path)

        try:
            response = self.session.request(
                method=method,
                url=url,
                timeout=self.timeout,
                json=payload,
            )
        except requests.RequestException as exc:
            raise IxiaClientError(f"request failed for {url}: {exc}") from exc

        if response.status_code not in expected:
            raise IxiaClientError(
                f"{method} {url} failed: status={response.status_code}, body={response.text[:1000]}"
            )

        if not response.text.strip():
            return {}

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type or response.text.strip().startswith("{") or response.text.strip().startswith("["):
            return response.json()

        return {"raw_text": response.text}

    def get(self, path: str) -> Any:
        return self._request("GET", path, expected=(200,))

    def post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("POST", path, expected=(200, 201, 202), payload=payload)

    def patch(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("PATCH", path, expected=(200,), payload=payload)

    # ------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------
    def get_sessions(self) -> List[Dict[str, Any]]:
        data = self.get("/sessions")
        return data if isinstance(data, list) else data.get("sessions", [])

    def set_session_id(self, session_id: int) -> None:
        self.session_id = session_id

    def resolve_session_id(self, session_id: Optional[int] = None) -> int:
        if session_id is not None:
            self.session_id = session_id
            return session_id

        if self.session_id is not None:
            return self.session_id

        sessions = self.get_sessions()
        if not sessions:
            raise IxiaClientError("no IxNetwork sessions found")

        first = sessions[0]
        session_id = int(first["id"])
        self.session_id = session_id
        return session_id

    def session_root(self, session_id: Optional[int] = None) -> str:
        sid = self.resolve_session_id(session_id)
        return f"/sessions/{sid}/ixnetwork"

    # ------------------------------------------------------------
    # Inventory helpers
    # ------------------------------------------------------------
    def get_inventory_ports(self) -> List[Dict[str, Any]]:
        return self.inventory.get("ports", [])

    def find_inventory_by_switch(self, switch: str) -> List[Dict[str, Any]]:
        return [p for p in self.get_inventory_ports() if p.get("switch") == switch]

    def find_inventory_by_ixia_port(self, ixia_port: str) -> Optional[Dict[str, Any]]:
        for item in self.get_inventory_ports():
            if item.get("ixia_port") == ixia_port:
                return item
        return None

    # ------------------------------------------------------------
    # Base discovery APIs
    # ------------------------------------------------------------
    def get_topologies(self, session_id: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.get(f"{self.session_root(session_id)}/topology")

    def get_vports(self, session_id: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.get(f"{self.session_root(session_id)}/vport")

    def get_traffic_items(self, session_id: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.get(f"{self.session_root(session_id)}/traffic/trafficItem")

    def get_statistics_views(self, session_id: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.get(f"{self.session_root(session_id)}/statistics/view")

    def get_globals(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        return self.get(f"{self.session_root(session_id)}/globals")

    def get_available_hardware(self) -> Any:
        return self.get("/availableHardware")

    # ------------------------------------------------------------
    # Href helpers
    # ------------------------------------------------------------

    def start_traffic_items_sequential(
        self,
        session_id: Optional[int] = None,
        interval_seconds: float = 0.1,
    ) -> List[Dict[str, Any]]:
        """
        Start traffic items one-by-one with delay (flow-by-flow behavior).
        """
        sid = self.resolve_session_id(session_id)
        root = self.session_root(sid)

        traffic_items = self.get_traffic_items(sid)
        print(f"IXIA traffic item count: {len(traffic_items)}")
        print(f"IXIA traffic items: {[item.get('name') for item in traffic_items]}")
        results = []

        for item in traffic_items:
            href = self.get_href(item)
            if not href:
                continue

            try:
                # Enable this traffic item
                self.patch(href, {"enabled": True})

                # Apply changes
                self.apply_traffic(sid)

                # Start traffic (this will include enabled items)
                result = self.start_traffic(sid)

                results.append({
                    "traffic_item": item.get("name"),
                    "status": "started",
                    "started_epoch": time.time(),
                })

                time.sleep(interval_seconds)

            except Exception as exc:
                results.append({
                    "traffic_item": item.get("name"),
                    "status": "failed",
                    "error": str(exc),
                })

        return results
    def get_href(self, obj: Dict[str, Any]) -> Optional[str]:
        if obj.get("href"):
            return obj["href"]
        links = obj.get("links", [])
        if links and isinstance(links, list):
            href = links[0].get("href")
            if href:
                return href
        return None

    def get_collection(self, parent_href: str, child_name: str) -> List[Dict[str, Any]]:
        try:
            data = self.get(f"{parent_href}/{child_name}")
            return data if isinstance(data, list) else []
        except Exception:
            return []

    # ------------------------------------------------------------
    # Topology / DG / protocol / NG discovery
    # ------------------------------------------------------------
    def get_device_groups_for_topology_href(self, topo_href: str) -> List[Dict[str, Any]]:
        return self.get_collection(topo_href, "deviceGroup")

    def get_network_groups_for_device_group_href(self, dg_href: str) -> List[Dict[str, Any]]:
        return self.get_collection(dg_href, "networkGroup")

    def get_ethernet_for_device_group_href(self, dg_href: str) -> List[Dict[str, Any]]:
        return self.get_collection(dg_href, "ethernet")

    def get_ipv4_for_ethernet_href(self, eth_href: str) -> List[Dict[str, Any]]:
        return self.get_collection(eth_href, "ipv4")

    def get_ipv6_for_ethernet_href(self, eth_href: str) -> List[Dict[str, Any]]:
        return self.get_collection(eth_href, "ipv6")

    def get_topology_details(self, session_id: Optional[int] = None) -> List[Dict[str, Any]]:
        topologies = self.get_topologies(session_id)
        details: List[Dict[str, Any]] = []

        for topo in topologies:
            topo_href = self.get_href(topo)
            topo_raw = topo
            if topo_href:
                try:
                    topo_raw = self.get(topo_href)
                except Exception:
                    topo_raw = topo

            device_groups: List[Dict[str, Any]] = []
            if topo_href:
                raw_dgs = self.get_device_groups_for_topology_href(topo_href)
                for dg in raw_dgs:
                    dg_href = self.get_href(dg)
                    dg_raw = dg
                    if dg_href:
                        try:
                            dg_raw = self.get(dg_href)
                        except Exception:
                            dg_raw = dg

                    ethernet = self.get_ethernet_for_device_group_href(dg_href) if dg_href else []
                    ethernet_details: List[Dict[str, Any]] = []
                    for eth in ethernet:
                        eth_href = self.get_href(eth)
                        eth_raw = eth
                        if eth_href:
                            try:
                                eth_raw = self.get(eth_href)
                            except Exception:
                                eth_raw = eth

                        ipv4 = self.get_ipv4_for_ethernet_href(eth_href) if eth_href else []
                        ipv6 = self.get_ipv6_for_ethernet_href(eth_href) if eth_href else []

                        ethernet_details.append({
                            "name": eth.get("name"),
                            "href": eth_href,
                            "raw": eth_raw,
                            "ipv4": ipv4,
                            "ipv6": ipv6,
                        })

                    network_groups = self.get_network_groups_for_device_group_href(dg_href) if dg_href else []

                    device_groups.append({
                        "name": dg.get("name"),
                        "id": dg.get("id"),
                        "href": dg_href,
                        "raw": dg_raw,
                        "ethernet": ethernet_details,
                        "network_groups": network_groups,
                    })

            details.append({
                "name": topo.get("name"),
                "id": topo.get("id"),
                "href": topo_href,
                "raw": topo_raw,
                "device_groups": device_groups,
            })

        return details

    def get_network_groups_for_topology(
        self,
        topology_name: Optional[str] = None,
        session_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        topologies = self.get_topology_details(session_id)

        for topo in topologies:
            if topology_name and topo.get("name") != topology_name:
                continue

            for dg in topo.get("device_groups", []):
                result.append({
                    "topology": topo.get("name"),
                    "device_group": dg.get("name"),
                    "network_groups": dg.get("network_groups", []),
                })

        return result

    # ------------------------------------------------------------
    # Traffic items
    # ------------------------------------------------------------
    def get_traffic_item_details(self, session_id: Optional[int] = None) -> List[Dict[str, Any]]:
        items = self.get_traffic_items(session_id)
        details: List[Dict[str, Any]] = []

        for item in items:
            href = self.get_href(item)
            obj = item
            if href:
                try:
                    obj = self.get(href)
                except Exception:
                    obj = item

            details.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "href": href,
                "raw": obj,
            })

        return details

    # ------------------------------------------------------------
    # Traffic control
    # ------------------------------------------------------------
    def apply_traffic(self, session_id: Optional[int] = None) -> Any:
        return self.post(f"{self.session_root(session_id)}/traffic/operations/apply", payload={})

    def start_traffic(self, session_id: Optional[int] = None) -> Any:
        root = self.session_root(session_id)
        return self.post(
            f"{root}/traffic/operations/start",
            payload={"arg1": f"{root}/traffic"},
        )

    def stop_traffic(self, session_id: Optional[int] = None) -> Any:
        root = self.session_root(session_id)
        return self.post(
            f"{root}/traffic/operations/stop",
            payload={"arg1": f"{root}/traffic"},
        )

    # ------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------
    def get_statistics_view_by_name(
        self,
        view_name: str,
        session_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        views = self.get_statistics_views(session_id)
        for view in views:
            if view.get("caption") == view_name or view.get("name") == view_name:
                return view
        return None

    def get_statistics_view_rows(self, view_name: str, session_id: int, page_size: int = 50) -> dict:
        views = self.get_statistics_views(session_id)
        matched = None

        for view in views or []:
            if str(view.get("caption") or "").strip() == view_name:
                matched = view
                break

        if not matched:
            raise IxiaClientError(f"statistics view '{view_name}' not found")

        href = None
        for link in matched.get("links", []) or []:
            if link.get("rel") == "meta":
                href = link.get("href")
                break

        if not href:
            view_id = matched.get("id")
            href = f"/api/v1/sessions/{session_id}/ixnetwork/statistics/view/{view_id}"

        # Smaller page request instead of unbounded /page
        try:
            page = self.get(f"{href}/page?pageSize={page_size}&pageNumber=1")
        except Exception:
            # fallback to legacy path if query style is unsupported
            page = self.get(f"{href}/page")

        return {
            "view": matched,
            "page": page,
        }


    def get_port_statistics(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        return self._safe_get_view_rows("Port Statistics", session_id, page_size=5)

    def _safe_get_view_rows(self, view_name: str, session_id: Optional[int] = None, page_size: int = 50) -> Dict[str, Any]:
        sid = self.resolve_session_id(session_id)

        views = self.get_statistics_views(sid)
        view = next((v for v in views if v.get("caption") == view_name), None)

        if not view:
            raise IxiaClientError(f"View '{view_name}' not found")

        view_id = view["id"]
        href = f"/api/v1/sessions/{sid}/ixnetwork/statistics/view/{view_id}"

        last_exc = None

        for attempt in range(2):
            try:

                page = self.get(f"{href}/page?pageSize={page_size}&pageNumber=1")

                return {
                    "view": view,
                    "page": page,
                }
            except Exception as exc:
                last_exc = exc
                time.sleep(2)

        raise IxiaClientError(f"Failed to fetch '{view_name}' after retries: {last_exc}")

    def get_flow_statistics(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        return self.get_statistics_view_rows("Flow Statistics", session_id)

    def get_traffic_item_statistics(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        return self.get_statistics_view_rows("Traffic Item Statistics", session_id)

    # ------------------------------------------------------------
    # Remote helper execution
    # ------------------------------------------------------------
    def run_remote_helper(self, remote_command: str) -> Dict[str, Any]:
        helper_host = self.helper_host.get("host")
        helper_user = self.helper_host.get("user", "root")

        if not helper_host:
            raise IxiaClientError("api_helper_host.host not found in ixia_inventory.json")

        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            f"{helper_user}@{helper_host}",
            remote_command,
        ]

        proc = subprocess.run(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if proc.returncode != 0:
            raise IxiaClientError(
                f"remote helper failed rc={proc.returncode}, stderr={proc.stderr.strip()}"
            )

        stdout_text = proc.stdout.strip()
        if not stdout_text:
            return {"stdout": "", "stderr": proc.stderr.strip()}

        try:
            return json.loads(stdout_text)
        except json.JSONDecodeError:
            return {
                "stdout": stdout_text,
                "stderr": proc.stderr.strip(),
            }

    
    def run_scale_toggle(
        self,
        topology: str,
        network_group: str,
        low: int,
        high: int,
        cycles: int = 1,
        settle: int = 30,
    ) -> Dict[str, Any]:
        cmd = (
            f"python3 /opt/ixia/ixia_event_runner.py "
            f"--api-server {shlex.quote(self.api_server)} "
            f"--topology {shlex.quote(topology)} "
            f"--event scale-toggle "
            f"--network-group {shlex.quote(network_group)} "
            f"--low {int(low)} "
            f"--high {int(high)} "
            f"--cycles {int(cycles)} "
            f"--settle {int(settle)} "
            f"--json"
        )
        return self.run_remote_helper(cmd)

    # ------------------------------------------------------------
    # High-level discovery snapshot
    # ------------------------------------------------------------
    def build_discovery_snapshot(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        sid = self.resolve_session_id(session_id)

        snapshot: Dict[str, Any] = {
            "api_server": self.api_server,
            "session_id": sid,
            "inventory_ports": self.get_inventory_ports(),
        }

        try:
            snapshot["sessions"] = self.get_sessions()
        except Exception as exc:
            snapshot["sessions_error"] = str(exc)

        try:
            snapshot["topologies"] = self.get_topology_details(sid)
        except Exception as exc:
            snapshot["topologies_error"] = str(exc)

        try:
            snapshot["vports"] = self.get_vports(sid)
        except Exception as exc:
            snapshot["vports_error"] = str(exc)

        try:
            snapshot["traffic_items"] = self.get_traffic_item_details(sid)
        except Exception as exc:
            snapshot["traffic_items_error"] = str(exc)

        try:
            snapshot["statistics_views"] = self.get_statistics_views(sid)
        except Exception as exc:
            snapshot["statistics_views_error"] = str(exc)

        return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ixia IxNetwork discovery and helper client")
    parser.add_argument("--inventory", default=DEFAULT_IXIA_INVENTORY)
    parser.add_argument("--api-server", default=None)
    parser.add_argument("--session-id", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--verify-tls", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sessions")
    subparsers.add_parser("topologies")
    subparsers.add_parser("traffic-items")
    subparsers.add_parser("vports")
    subparsers.add_parser("inventory-ports")
    subparsers.add_parser("discovery-snapshot")

    ng_parser = subparsers.add_parser("network-groups")
    ng_parser.add_argument("--topology-name", default=None)

    helper_parser = subparsers.add_parser("scale-toggle")
    helper_parser.add_argument("--topology", required=True)
    helper_parser.add_argument("--network-group", required=True)
    helper_parser.add_argument("--low", type=int, required=True)
    helper_parser.add_argument("--high", type=int, required=True)
    helper_parser.add_argument("--cycles", type=int, default=1)
    helper_parser.add_argument("--settle", type=int, default=30)

    stats_parser = subparsers.add_parser("stats")
    stats_parser.add_argument(
        "--view",
        required=True,
        choices=["port", "flow", "traffic-item"],
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        inventory = load_json_file(args.inventory)
        api_server = args.api_server or inventory.get("ixnetwork_api_server")
        if not api_server:
            raise IxiaClientError("api server not provided and not found in inventory")

        client = IxiaClient(
            api_server=api_server,
            inventory_path=args.inventory,
            timeout=args.timeout,
            verify_tls=args.verify_tls,
        )

        if args.command == "sessions":
            result = client.get_sessions()

        elif args.command == "topologies":
            result = client.get_topology_details(args.session_id)

        elif args.command == "traffic-items":
            result = client.get_traffic_item_details(args.session_id)

        elif args.command == "vports":
            result = client.get_vports(args.session_id)

        elif args.command == "inventory-ports":
            result = client.get_inventory_ports()

        elif args.command == "network-groups":
            result = client.get_network_groups_for_topology(
                topology_name=args.topology_name,
                session_id=args.session_id,
            )

        elif args.command == "discovery-snapshot":
            result = client.build_discovery_snapshot(args.session_id)

        elif args.command == "scale-toggle":
            result = client.run_scale_toggle(
                topology=args.topology,
                network_group=args.network_group,
                low=args.low,
                high=args.high,
                cycles=args.cycles,
                settle=args.settle,
            )

        elif args.command == "stats":
            if args.view == "port":
                result = client.get_port_statistics(args.session_id)
            elif args.view == "flow":
                result = client.get_flow_statistics(args.session_id)
            elif args.view == "traffic-item":
                result = client.get_traffic_item_statistics(args.session_id)
            else:
                raise IxiaClientError(f"unsupported stats view {args.view}")

        else:
            raise IxiaClientError(f"unsupported command {args.command}")

        print(json.dumps(result, indent=2))
        return 0

    except Exception as exc:  # noqa
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
