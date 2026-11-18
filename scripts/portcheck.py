"""Host port checks for the local stack. Standard library only.

Two jobs share one decision rule:
  * `python3 -I scripts/portcheck.py preflight` (run by `make up`) refuses to start when a host port the
    kit itself publishes is already in use. Administration ports are not checked: the kit never publishes them,
    so a listener there is another process, and the end-to-end test decides from the kit's own publication.
  * the end-to-end test asks `admin_findings` whether the kit itself publishes an administration port.
    A listener that belongs to another process is not a finding: only the kit's own publication is.
"""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "gateway" / "compose.yaml"
COMPOSE = ["docker", "compose", "-f", str(COMPOSE_FILE)]
# Administration ports of Envoy (1976 ai listener, 19000 admin), the guard's ext_proc (9002) and OPA (8181).
ADMIN_PORTS = (1976, 19000, 9002, 8181)
OVERRIDES = {"aigw": "CRFR_GATEWAY_PORT", "keycloak": "CRFR_KEYCLOAK_PORT"}
FAILING = {"published-by-kit", "host-network-listener"}


def is_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        socket.create_connection((host, port), timeout=2).close()
    except OSError:
        return False
    return True


def published_ports(ps_json_lines: str) -> set[int]:
    """Host ports published by the kit's containers, from `docker compose ps --format json`."""
    ports = set()
    for line in ps_json_lines.splitlines():
        if not line.strip():
            continue
        for publisher in json.loads(line).get("Publishers") or []:
            if publisher.get("PublishedPort"):
                ports.add(int(publisher["PublishedPort"]))
    return ports


def verdict(port: int, published: set[int], listening: bool, host_network: bool = False) -> str:
    """What a port on the host means for the kit.

    published-by-kit: a kit container publishes it (listener or not): a leak, whoever answers.
    host-network-listener: a kit container shares the host network and something listens: assumed the kit's.
    other-process: something listens, and the kit publishes nothing there: not the kit's doing.
    closed: nothing listens.
    """
    if port in published:
        return "published-by-kit"
    if listening:
        return "host-network-listener" if host_network else "other-process"
    return "closed"


def admin_findings(published: set[int], listening, host_network: bool, ports=ADMIN_PORTS) -> list[tuple[int, str]]:
    findings = []
    for port in ports:
        result = verdict(port, published, listening(port), host_network)
        if result in FAILING:
            findings.append((port, result))
    return findings


def wanted_ports(config: dict) -> dict[int, tuple[str, str]]:
    """Host ports the kit will publish, with the service and the variable that overrides each."""
    wanted = {}
    for name, service in (config.get("services") or {}).items():
        for entry in service.get("ports") or []:
            if entry.get("published"):
                wanted[int(entry["published"])] = (
                    name,
                    OVERRIDES.get(name, f"the ports of {name} in gateway/compose.yaml"),
                )
    return wanted


def preflight(wanted: dict[int, tuple[str, str]], running: set[int], listening) -> list[str]:
    """Messages for the ports that are taken before the kit starts. `running` are the kit's own published ports."""
    problems = []
    for port, (service, variable) in sorted(wanted.items()):
        if port not in running and listening(port):
            problems.append(
                f"port {port} on 127.0.0.1 is already in use, and the kit needs it for {service}. "
                f"Stop the process that holds it (find it with: ss -ltnp 'sport = :{port}'), "
                f"or publish {service} elsewhere: {variable}=<free port> make up"
            )
    return problems


def docker_json(*args: str) -> str:
    return subprocess.run([*COMPOSE, *args], check=True, capture_output=True, text=True, timeout=60).stdout


def uses_host_network() -> bool:
    ids = subprocess.run([*COMPOSE, "ps", "-q"], check=True, capture_output=True, text=True, timeout=60).stdout.split()
    if not ids:
        return False
    modes = subprocess.run(
        ["docker", "inspect", "--format", "{{.HostConfig.NetworkMode}}", *ids],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.split()
    return "host" in modes


def main(argv: list[str]) -> int:
    if argv[:1] != ["preflight"]:
        print("usage: portcheck.py preflight", file=sys.stderr)
        return 2
    if os.environ.get("CRFR_SKIP_PREFLIGHT") == "1":
        print("preflight: skipped (CRFR_SKIP_PREFLIGHT=1)")
        return 0
    wanted = wanted_ports(json.loads(docker_json("config", "--format", "json")))
    running = published_ports(docker_json("ps", "--format", "json"))
    print("preflight: the kit publishes " + ", ".join(f"{p} ({s})" for p, (s, _) in sorted(wanted.items())))
    problems = preflight(wanted, running, is_listening)
    for problem in problems:
        print(f"preflight: {problem}", file=sys.stderr)
    if problems:
        print("preflight: nothing was started. To start anyway: CRFR_SKIP_PREFLIGHT=1 make up", file=sys.stderr)
        return 1
    print("preflight: ports free")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
