import json

from conftest import bearer, body

from crfr_guard.audit import read_segments
from crfr_guard.engine import Exchange
from crfr_guard.policy import PolicyDecision, PolicyUnavailable

OK = json.dumps({"usage": {"input_tokens": 40, "output_tokens": 20}}).encode()


def admit(guard, headers=None, raw=None):
    exchange = Exchange()
    refusal = guard.on_request(exchange, headers or bearer(), raw or body())
    return exchange, refusal


def complete(guard, exchange, raw=OK, status=200, content_type="application/json"):
    exchange.response_status, exchange.content_type = status, content_type
    guard.on_response_chunk(exchange, raw)
    guard.on_response_end(exchange)


def decisions(tmp_path):
    return [json.loads(line) for line in read_segments(tmp_path / "audit")]


def test_admits_and_charges(guard, tmp_path):
    exchange, refusal = admit(guard)
    assert refusal is None
    complete(guard, exchange)
    assert guard.ledger.tokens_today("user", "alice") == 60
    assert abs(guard.ledger.cost_this_month("app", "demo-app") - (40 * 3 + 20 * 15) / 1e6) < 1e-12
    log = decisions(tmp_path)
    assert [e["event"] for e in log] == ["request", "response"]
    assert "bonjour" not in json.dumps(log), "the decision log must not contain the prompt"


def test_policy_input(guard):
    admit(guard, raw=body(stream=True))
    sent = guard.opa.inputs[-1]
    assert sent["model"] == "claude-sonnet-5" and sent["stream"] is True
    assert sent["groups"] == ["claude-users", "team-risk"] and sent["team"] == "team-risk"
    assert sent["pii"] == {"residual": [], "pseudonymised": {}} and sent["max_tokens"] == 64


def test_residual_identifier_reaches_policy(guard):
    admit(guard, raw=body(text="mon IBAN FR76 0000 0012 3412 3456 7890 151"))
    assert guard.opa.inputs[-1]["pii"]["residual"] == ["IBAN_FR"]


def test_policy_refusal_and_failure(guard):
    guard.opa.decision = PolicyDecision(False, ("model-not-allowed", "not-pseudonymised"))
    _, refusal = admit(guard)
    assert (refusal.status, refusal.reason) == (403, "policy")
    assert b"not-pseudonymised" in refusal.body()
    guard.opa.error = PolicyUnavailable("connection refused")
    _, refusal = admit(guard)
    assert (refusal.status, refusal.reason) == (503, "policy-unavailable")


def test_user_quota_blocks_next_request(guard):
    for _ in range(2):  # 60 then 120 tokens: the second request is admitted (60 < 100) and overshoots
        exchange, refusal = admit(guard)
        assert refusal is None
        complete(guard, exchange)
    _, refusal = admit(guard)
    assert (refusal.status, refusal.reason) == (429, "quota-user")
    _, other = admit(guard, headers=bearer(user="bob"))
    assert other is None, "the quota is per user"


def test_quota_override(guard):
    for _ in range(3):
        exchange, refusal = admit(guard, headers=bearer(user="vip"))
        assert refusal is None
        complete(guard, exchange)


def test_app_quota_counts_all_users(guard):
    big = json.dumps({"usage": {"input_tokens": 990}}).encode()
    exchange, _ = admit(guard, headers=bearer(user="u1", app="shared"))
    complete(guard, exchange, big)
    exchange, _ = admit(guard, headers=bearer(user="u2", app="shared"))
    complete(guard, exchange, json.dumps({"usage": {"input_tokens": 20}}).encode())
    _, refusal = admit(guard, headers=bearer(user="u3", app="shared"))
    assert refusal.reason == "quota-app"


def test_budget(guard):
    _, refusal = admit(guard, headers=bearer(app="tiny"))
    assert (refusal.status, refusal.reason) == (429, "budget-app")


def test_unpriced_model_refused(guard):
    _, refusal = admit(guard, raw=body(model="claude-unknown"))
    assert (refusal.status, refusal.reason) == (403, "no-price")


def test_kill_switches(guard):
    guard.ledger.set_switch("app", "demo-app", "leaked")
    _, refusal = admit(guard)
    assert (refusal.status, refusal.reason) == (403, "kill-switch-app")
    guard.ledger.set_switch("global", "*", "incident")
    _, refusal = admit(guard, headers=bearer(app="other"))
    assert (refusal.status, refusal.reason) == (503, "kill-switch-global")
    assert guard.opa.inputs == [], "a stopped gateway does not even ask the policy engine"


def test_bad_bodies(guard):
    assert admit(guard, raw=b"{nope")[1].status == 400
    assert admit(guard, raw=b"[1]")[1].status == 400
    assert admit(guard, headers={"x-request-id": "1"})[1].status == 401


def test_no_charge_on_error_or_missing_usage(guard, tmp_path):
    exchange, _ = admit(guard)
    complete(guard, exchange, b'{"type":"error"}', status=500)
    exchange, _ = admit(guard)
    complete(guard, exchange, b'{"id":"x"}')
    assert guard.ledger.tokens_today("user", "alice") == 0
    assert decisions(tmp_path)[-1]["usage_missing"] is True


def test_streamed_usage_split_across_chunks(guard):
    exchange, _ = admit(guard)
    exchange.response_status, exchange.content_type = 200, "text/event-stream"
    stream = (
        b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":7}}}\n\n'
        + b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"text":"'
        + b"x" * 5000
        + b'"}}\n\n'
        + b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":9}}'
    )
    for i in range(0, len(stream), 37):
        guard.on_response_chunk(exchange, stream[i : i + 37])
    assert len(exchange.response_body) < 300, "text deltas are not kept in memory"
    guard.on_response_end(exchange)
    assert guard.ledger.tokens_today("user", "alice") == 16


def test_response_buffer_is_bounded(guard):
    exchange, _ = admit(guard)
    exchange.response_status = 200
    guard.config = guard.config.__class__(**{**guard.config.__dict__, "max_buffer_bytes": 10})
    guard.on_response_chunk(exchange, b"x" * 50)
    assert len(exchange.response_body) == 10 and exchange.truncated
