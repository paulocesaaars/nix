"""Confere a ligação entre os cenários do BDD (`BDD.md` e `bdd/`) e os testes.

O `BDD.md` é o índice dos casos de uso; os cenários ficam em `bdd/*.md`. Erra se
o índice e a pasta divergirem. Lista os cenários automatizáveis sem teste
(`@pytest.mark.bdd("HU-03.2")`) e os testes que apontam para um ID que não
existe. Cenários `@manual` ficam fora da cobertura e aparecem como checklist.

Uso:
  python scripts/check_bdd.py            # cenário sem teste é só aviso
  python scripts/check_bdd.py --strict   # cenário sem teste também falha
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"

_INDEX_LINK = re.compile(r"\(\./bdd/([^)]+\.md)\)")
_TAG = re.compile(r"@([A-Za-z][\w.-]*)")
_SCENARIO_ID = re.compile(r"^[A-Z]+-\d+\.\d+$")
_SCENARIO_LINE = re.compile(r"^\s*(Cenário|Esquema do Cenário|Scenario)\b")
_FEATURE_LINE = re.compile(r"^\s*(Funcionalidade|Feature)\b")
_TEST_MARK = re.compile(r"mark\.bdd\(([^)]*)\)")
_QUOTED = re.compile(r"[\"']([^\"']+)[\"']")


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    title: str
    manual: bool


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def read_scenarios(text: str, source: str) -> list[Scenario]:
    """Cenários de um arquivo do BDD, com as tags herdadas da funcionalidade."""
    scenarios: list[Scenario] = []
    feature_tags: set[str] = set()
    pending: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("@"):
            pending |= set(_TAG.findall(stripped))
        elif _FEATURE_LINE.match(line):
            feature_tags, pending = pending, set()
        elif _SCENARIO_LINE.match(line):
            ids = [tag for tag in pending if _SCENARIO_ID.match(tag)]
            if len(ids) != 1:
                _fail(f"Cenário sem ID único em {source}: {stripped!r}. Adicione uma tag como @HU-03.2.")
            title = stripped.split(":", 1)[-1].strip()
            scenarios.append(Scenario(ids[0], title, "manual" in (pending | feature_tags)))
            pending = set()
        elif stripped and not stripped.startswith("#"):
            pending = set()
    return scenarios


def read_bdd(root: Path) -> list[Scenario]:
    """Lê todos os `bdd/*.md` e confere se o índice do `BDD.md` bate com a pasta."""
    index = root / "BDD.md"
    folder = root / "bdd"
    if not index.is_file():
        _fail("BDD.md não encontrado na raiz do repositório. Crie o arquivo (pode ficar em branco).")
    listed = set(_INDEX_LINK.findall(index.read_text(encoding="utf-8")))
    present = {path.name for path in folder.glob("*.md")} if folder.is_dir() else set()
    missing_files = sorted(listed - present)
    if missing_files:
        _fail(f"O índice do BDD.md aponta para arquivos que não existem em bdd/: {', '.join(missing_files)}.")
    unlisted = sorted(present - listed)
    if unlisted:
        _fail(f"Arquivos em bdd/ fora do índice do BDD.md: {', '.join(unlisted)}. Acrescente uma linha ao índice.")
    scenarios: list[Scenario] = []
    for name in sorted(present):
        scenarios.extend(read_scenarios((folder / name).read_text(encoding="utf-8"), f"bdd/{name}"))
    return scenarios


def read_test_ids(tests_dir: Path) -> dict[str, list[str]]:
    """IDs de cenário citados em `@pytest.mark.bdd(...)`, com os arquivos que os citam."""
    found: dict[str, list[str]] = {}
    if not tests_dir.is_dir():
        return found
    for path in sorted(tests_dir.rglob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        for args in _TEST_MARK.findall(source):
            for scenario_id in _QUOTED.findall(args):
                found.setdefault(scenario_id, []).append(path.relative_to(ROOT).as_posix())
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Confere a cobertura dos cenários do BDD pelos testes.")
    parser.add_argument("--strict", action="store_true", help="falha também quando um cenário não tem teste")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    scenarios = read_bdd(ROOT)
    counts = Counter(s.scenario_id for s in scenarios)
    duplicated = sorted(sid for sid, count in counts.items() if count > 1)
    if duplicated:
        _fail(f"IDs repetidos no BDD: {', '.join(duplicated)}. Cada cenário precisa de um ID próprio.")

    known = {s.scenario_id for s in scenarios}
    tested = read_test_ids(TESTS_DIR)
    unknown = {sid: files for sid, files in tested.items() if sid not in known}
    automated = [s for s in scenarios if not s.manual]
    missing = [s for s in automated if s.scenario_id not in tested]
    manual = [s for s in scenarios if s.manual]

    covered = len(automated) - len(missing)
    print(f"BDD: {covered}/{len(automated)} cenários automatizáveis com teste; {len(manual)} manuais.")
    if missing:
        print("\nCenários sem teste:")
        for s in missing:
            print(f"  - {s.scenario_id} {s.title}")
    if manual:
        print("\nChecklist manual (conferir antes da release):")
        for s in manual:
            print(f"  - [ ] {s.scenario_id} {s.title}")
    if unknown:
        print("\nTestes apontando para cenário inexistente no BDD:", file=sys.stderr)
        for sid, files in sorted(unknown.items()):
            print(f"  - {sid} em {', '.join(files)}", file=sys.stderr)
        _fail("Corrija o ID no teste ou adicione o cenário em bdd/.")
    if missing and args.strict:
        _fail("Há cenários sem teste. Escreva os testes ou marque o cenário como @manual.")


if __name__ == "__main__":
    main()
