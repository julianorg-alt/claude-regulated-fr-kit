from pathlib import Path

from crfr import traceability as tr

ROOT = Path(__file__).resolve().parents[2]


def write(root: Path, controls: str, texts: str) -> None:
    (root / "compliance").mkdir()
    (root / "docs" / "sources").mkdir(parents=True)
    (root / "compliance" / "controls.toml").write_text(controls)
    (root / "compliance" / "texts.toml").write_text(texts)
    (root / "docs" / "sources" / "verifications.md").write_text("| V1 | fait |\n")
    (root / "Makefile").write_text("eval: x\n")
    (root / "t.py").write_text("def test_ok():\n    pass\n\nclass Suite:\n    def test_m(self):\n        pass\n")
    (root / "m.tftest.hcl").write_text('run "plan_ok" {\n}\n')
    (root / "p_test.rego").write_text("test_rule if {\n}\n")


TEXT = '[[text]]\nid = "T1"\ntitle = "t"\nreference = "r"\nurl = "u"\nverification = "V1"\n'


def test_references_of_every_kind_resolve(tmp_path):
    tests = '["pytest:t.py::test_ok", "unittest:t.py::Suite.test_m", "tftest:m.tftest.hcl::plan_ok", ' \
            '"rego:p_test.rego::test_rule", "make:eval"]'  # fmt: skip
    write(tmp_path, f'[[control]]\nid = "C1"\ntitle = "c"\ntexts = ["T1"]\ntests = {tests}\n', TEXT)
    assert tr.check(tmp_path) == []
    assert "C1" in tr.render(tmp_path) and "vérifié (V1)" in tr.render(tmp_path)


def test_orphans_and_dangling_references_are_reported(tmp_path):
    controls = (
        '[[control]]\nid = "C1"\ntitle = "c"\ntexts = []\ntests = ["pytest:t.py::test_missing"]\n'
        '[[control]]\nid = "C2"\ntitle = "c"\ntexts = ["T9"]\ntests = []\n'
    )
    write(tmp_path, controls, TEXT + TEXT.replace('"T1"', '"T2"').replace('"V1"', '"V7"'))
    messages = {str(p) for p in tr.check(tmp_path)}
    assert "C1: orphan control: no text" in messages
    assert "C2: orphan control: no test" in messages
    assert "C2: unknown text T9" in messages
    assert "C1: test_missing not found in t.py" in messages
    assert "T1: text cited by no control" in messages
    assert "T2: verification V7 not in verifications.md" in messages


def test_repository_matrix_is_complete_and_current():
    assert tr.check(ROOT) == []
    assert (ROOT / tr.MATRIX).read_text(encoding="utf-8") == tr.render(ROOT)


CONTROL = '[[control]]\nid = "C1"\ntitle = "c"\ntexts = ["T1"]\ntests = ["pytest:t.py::test_ok"]\n'


def template(texts: str = '["T1"]', sections: str = '["A", "B"]') -> str:
    return f'[[template]]\nid = "M1"\npath = "m.md"\ntitle = "m"\ntexts = {texts}\nsections = {sections}\n'


def test_template_with_its_sections_and_known_controls_passes(tmp_path):
    write(tmp_path, CONTROL, TEXT + TEXT.replace('"T1"', '"T2"'))
    (tmp_path / "compliance" / "templates.toml").write_text(template('["T2"]'))
    (tmp_path / "m.md").write_text("# M\n\nVoir C1.\n\n## A\n\nx\n\n## B\n")
    assert tr.check(tmp_path) == []  # T2 is used by the template only
    assert "M1 : m" in tr.render(tmp_path)


def test_template_problems_are_reported(tmp_path):
    write(tmp_path, CONTROL, TEXT)
    (tmp_path / "compliance" / "templates.toml").write_text(
        template('["T1", "T9"]') + template().replace('"M1"', '"M2"').replace('"m.md"', '"absent.md"')
    )
    (tmp_path / "m.md").write_text("# M\n\nVoir C1 et C7.\n\n## B\n\n## A\n")
    messages = {str(p) for p in tr.check(tmp_path)}
    assert "M1: unknown text T9" in messages
    assert "M1: cites unknown control C7" in messages
    assert "M1: section 'B' missing or out of order" in messages  # A is found after B, so B comes too early
    assert "M2: no file absent.md" in messages
