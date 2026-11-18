"""Host port checks: a port taken by another process is not a port published by the kit."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("portcheck", ROOT / "scripts" / "portcheck.py")
portcheck = importlib.util.module_from_spec(spec)
sys.modules["portcheck"] = portcheck
spec.loader.exec_module(portcheck)


def ps_line(service, *publishers):
    return json.dumps(
        {
            "Service": service,
            "Publishers": [
                {"URL": url, "TargetPort": 1, "PublishedPort": port, "Protocol": "tcp"} for url, port in publishers
            ],
        }
    )


PS = "\n".join(
    [
        ps_line("aigw", ("127.0.0.1", 1975)),
        ps_line("keycloak", ("127.0.0.1", 8081)),
        ps_line("opa", ("", 0)),  # exposed inside the network only: PublishedPort 0
    ]
)


def test_published_ports_come_from_the_compose_publishers():
    assert portcheck.published_ports(PS) == {1975, 8081}
    assert portcheck.published_ports("") == set()


def test_port_taken_by_another_process_is_not_a_kit_failure():
    # The VPS case: something else listens on 8181 before `make up`; the kit publishes nothing there.
    verdict = portcheck.verdict(8181, published={1975, 8081}, listening=True)
    assert verdict == "other-process"
    assert verdict not in portcheck.FAILING


def test_admin_port_published_by_the_kit_fails_even_when_closed_to_a_probe():
    for listening in (True, False):
        verdict = portcheck.verdict(8181, published={1975, 8181}, listening=listening)
        assert verdict == "published-by-kit"
        assert verdict in portcheck.FAILING


def test_host_network_listener_is_a_kit_failure_but_a_closed_port_is_not():
    assert portcheck.verdict(9002, published=set(), listening=True, host_network=True) == "host-network-listener"
    assert portcheck.verdict(9002, published=set(), listening=False, host_network=True) == "closed"
    assert "host-network-listener" in portcheck.FAILING


def test_admin_findings_only_list_failing_ports():
    findings = portcheck.admin_findings(
        published={1975, 19000}, listening=lambda port: port in {8181, 19000}, host_network=False
    )
    assert findings == [(19000, "published-by-kit")]


def test_no_finding_when_the_kit_publishes_no_admin_port_whoever_listens():
    assert portcheck.admin_findings(published={1975, 8081}, listening=lambda port: True, host_network=False) == []


def test_preflight_names_the_port_and_the_override():
    wanted = {8081: ("keycloak", "CRFR_KEYCLOAK_PORT"), 1975: ("aigw", "CRFR_GATEWAY_PORT")}
    problems = portcheck.preflight(wanted, running=set(), listening=lambda port: port == 8081)
    text = "\n".join(problems)
    assert len(problems) == 1
    assert "8081" in text and "keycloak" in text and "CRFR_KEYCLOAK_PORT" in text and "1975" not in text


def test_preflight_ignores_ports_the_running_kit_already_publishes():
    wanted = {8081: ("keycloak", "CRFR_KEYCLOAK_PORT")}
    assert portcheck.preflight(wanted, running={8081}, listening=lambda port: True) == []


def test_preflight_passes_on_free_ports():
    wanted = {8081: ("keycloak", "CRFR_KEYCLOAK_PORT")}
    assert portcheck.preflight(wanted, running=set(), listening=lambda port: False) == []


def test_preflight_ignores_a_foreign_listener_on_an_administration_port_the_kit_does_not_publish():
    """Regression, owner's VPS: an unrelated host service on 127.0.0.1:8181 blocked `make up`."""
    wanted = {8081: ("keycloak", "CRFR_KEYCLOAK_PORT"), 1975: ("aigw", "CRFR_GATEWAY_PORT")}
    listening = lambda port: port in portcheck.ADMIN_PORTS  # noqa: E731
    assert portcheck.preflight(wanted, running=set(), listening=listening) == []
    assert 8181 in portcheck.ADMIN_PORTS and 8181 not in wanted
