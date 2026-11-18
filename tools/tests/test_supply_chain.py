from pathlib import Path

from crfr import supply_chain as sc

DIGEST = "@sha256:" + "a" * 64
SHA = "@" + "b" * 40


def test_workflow_requires_commit_sha():
    text = f"steps:\n  - uses: actions/checkout@v4\n  - uses: actions/setup-python{SHA}\n  - uses: ./local\n"
    findings = sc.check_workflow(Path("ci.yml"), text)
    assert len(findings) == 1 and "actions/checkout@v4" in findings[0].message


def test_images_need_digest_and_no_latest():
    text = f"image: nginx:latest\nimage: envoy:v1{DIGEST}\nimage: busybox:1.36\n"
    messages = [f.message for f in sc.check_images(Path("x.yaml"), text)]
    assert any("latest" in m for m in messages)
    assert sum("without sha256" in m for m in messages) == 2


def test_dockerfile_from():
    text = f"FROM python:3.13-slim\nFROM python:3.13-slim{DIGEST} AS run\nFROM scratch\n"
    findings = sc.check_images(Path("Dockerfile"), text)
    assert len(findings) == 1


def test_requirements_pins():
    text = "presidio-analyzer==2.2.360\nspacy>=3.8\nflask\n# comment\n--hash=sha256:abc\n"
    findings = sc.check_requirements(Path("requirements.txt"), text)
    assert [f.line for f in findings] == [2, 3]


def test_package_json_needs_exact_versions_and_a_lockfile():
    good = '{"devDependencies": {"promptfoo": "0.125.1"}}'
    assert sc.check_package_json(Path("package.json"), good, True) == []
    bad = '{"dependencies": {"a": "^1.2.3", "b": "latest"}, "devDependencies": {"c": "~0.1.0"}}'
    assert len(sc.check_package_json(Path("package.json"), bad, True)) == 3
    (missing_lock,) = sc.check_package_json(Path("package.json"), good, False)
    assert "package-lock.json" in missing_lock.message


def test_scan_skips_fixtures(tmp_path):
    (tmp_path / "tools" / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tools" / "tests" / "fixtures" / "bad.yaml").write_text("image: nginx:latest\n")
    (tmp_path / "deploy.yaml").write_text("image: nginx:latest\n")
    findings = sc.scan(tmp_path)
    assert {str(f.path) for f in findings} == {"deploy.yaml"}


def test_repository_passes_its_own_gate():
    root = Path(__file__).resolve().parents[2]
    assert sc.scan(root) == []
