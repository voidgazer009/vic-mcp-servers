#!/usr/bin/env python3
"""Vic MCP automated review (see REVIEW_STANDARD.md).

Usage (from repo root, inside an env with the server's dependencies + pytest + jsonschema):
    python tools/audit.py servers/foreign-trade/export-quote [--json]

Checks every 🤖 item: hard gates G2-G7, G9 and the automatic parts of B, C, D, E, F.
Human (👤) items are listed as reminders and must be confirmed in reports/.
Exit code 0 only when every automated hard gate passes.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{20,}", r"ghp_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}", r"AKIA[0-9A-Z]{16}",
    r"AIza[0-9A-Za-z\-_]{35}", r"xox[baprs]-[A-Za-z0-9-]{10,}", r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
    r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"\s]{12,}['\"]",
]
FORBIDDEN = [r"\beval\(", r"\bexec\(", r"os\.system\(", r"shell\s*=\s*True", r"pickle\.loads\("]


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, bool, float, float, str]] = []

    def gate(self, code: str, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((code, name, ok, 0, 0, detail))

    def score(self, code: str, name: str, got: float, max_: float, detail: str = "") -> None:
        self.rows.append((code, name, got >= max_, got, max_, detail))

    @property
    def gates_ok(self) -> bool:
        return all(ok for c, _, ok, _, mx, _ in self.rows if c.startswith("G"))

    def totals(self) -> tuple[float, float]:
        got = sum(g for c, _, _, g, mx, _ in self.rows if not c.startswith("G"))
        mx = sum(m for c, _, _, _, m, _ in self.rows if not c.startswith("G"))
        return got, mx


def find_package(server_dir: Path) -> str:
    src = server_dir / "src"
    pkgs = [p.name for p in src.iterdir() if (p / "__init__.py").exists()] if src.exists() else []
    if len(pkgs) != 1:
        raise SystemExit(f"Expected exactly one package under {src}, found {pkgs}")
    return pkgs[0]


async def protocol_checks(server_dir: Path, pkg: str, rep: Report) -> dict:
    from mcp import Client, StdioServerParameters

    env = {**os.environ, "PYTHONPATH": str(server_dir / "src")}
    params = StdioServerParameters(command=sys.executable, args=["-m", pkg], env=env)
    info: dict = {}
    try:
        async with Client(params, read_timeout_seconds=30) as c:
            rep.gate("G2", "Starts over stdio and completes discovery", True)
            tools = (await c.list_tools()).tools
            info["tools"] = tools
            names_ok = bool(tools) and all(re.fullmatch(r"[a-z][a-z0-9_]{2,63}", t.name) for t in tools)
            rep.gate("G3", "tools/list returns snake_case tools", names_ok, f"{len(tools)} tools: {', '.join(t.name for t in tools)}")

            # G7: empty / wrong arguments must come back as isError, server must survive
            crashed, not_error = [], []
            for t in tools:
                required = t.input_schema.get("required", [])
                if not required:
                    continue
                try:
                    r = await c.call_tool(t.name, {})
                    if not r.is_error:
                        not_error.append(t.name)
                except Exception as e:  # noqa: BLE001
                    crashed.append(f"{t.name}: {type(e).__name__}")
            await c.list_tools()  # still alive?
            rep.gate("G7", "Invalid input -> isError tool result, no crash", not crashed and not not_error,
                     "; ".join(crashed + [f"{n} accepted empty args" for n in not_error]))

            try:
                info["prompts"] = (await c.list_prompts()).prompts
            except Exception:  # noqa: BLE001
                info["prompts"] = []
            try:
                info["resources"] = (await c.list_resources()).resources
            except Exception:  # noqa: BLE001
                info["resources"] = []
    except Exception as e:  # noqa: BLE001
        rep.gate("G2", "Starts over stdio and completes discovery", False, f"{type(e).__name__}: {e}")
    return info


def scan_files(server_dir: Path) -> list[Path]:
    return [p for p in server_dir.rglob("*") if p.is_file() and ".venv" not in p.parts and "__pycache__" not in p.parts
            and p.suffix in {".py", ".ts", ".js", ".json", ".toml", ".md", ".yaml", ".yml", ".env", ".txt"}]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print(__doc__)
        return 2
    server_dir = (ROOT / args[0]).resolve()
    rep = Report()
    pkg = find_package(server_dir)
    sys.path.insert(0, str(server_dir / "src"))

    info = asyncio.run(protocol_checks(server_dir, pkg, rep))
    tools = info.get("tools", [])

    # G4 tests
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header"], cwd=server_dir,
                          capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(server_dir / "src")})
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-200:]
    has_proto_test = any("from mcp import Client" in p.read_text() for p in (server_dir / "tests").glob("test_*.py")) \
        if (server_dir / "tests").exists() else False
    rep.gate("G4", "pytest passes, incl. a protocol-level Client test", proc.returncode == 0 and has_proto_test,
             tail + ("" if has_proto_test else " | no test uses mcp.Client"))

    files = scan_files(server_dir)
    # G5 secrets
    hits = []
    for p in files:
        txt = p.read_text(errors="ignore")
        for pat in SECRET_PATTERNS:
            if re.search(pat, txt):
                hits.append(f"{p.relative_to(server_dir)} ~ {pat[:20]}")
    rep.gate("G5", "No secrets committed", not hits, "; ".join(hits))

    # G6 dangerous calls + destructive annotation
    bad = []
    for p in files:
        if p.suffix == ".py" and "tests" not in p.parts:
            for pat in FORBIDDEN:
                if re.search(pat, p.read_text(errors="ignore")):
                    bad.append(f"{p.name} ~ {pat}")
    rep.gate("G6", "No eval/exec/shell; destructive tools annotated", not bad, "; ".join(bad))

    # G9 packaging
    pyproject = server_dir / "pyproject.toml"
    sj = server_dir / "server.json"
    lic = (ROOT / "LICENSE").exists() or (server_dir / "LICENSE").exists()
    schema_ok, schema_msg, sjd = False, "", {}
    if sj.exists():
        try:
            import jsonschema

            sjd = json.loads(sj.read_text())
            cache = ROOT / ".cache" / (Path(sjd["$schema"]).parent.name + "-server.schema.json")
            if not cache.exists():
                cache.parent.mkdir(exist_ok=True)
                cache.write_bytes(urllib.request.urlopen(sjd["$schema"], timeout=20).read())
            jsonschema.validate(sjd, json.loads(cache.read_text()))
            schema_ok = True
        except Exception as e:  # noqa: BLE001
            schema_msg = f"{type(e).__name__}: {str(e)[:160]}"
    rep.gate("G9", "LICENSE + pyproject + server.json valid vs official schema", lic and pyproject.exists() and schema_ok,
             schema_msg or ("" if lic else "no LICENSE"))

    # ---------------- B. spec compliance (25)
    py = tomllib.loads(pyproject.read_text()) if pyproject.exists() else {}
    deps = " ".join(py.get("project", {}).get("dependencies", []))
    rep.score("B1", "Official SDK current major (mcp>=2)", 3 if re.search(r"mcp\s*>=\s*2", deps) else 0, 3, deps)

    srv_mod = __import__(f"{pkg}.server", fromlist=["mcp"])
    srv = getattr(srv_mod, "mcp", None)
    meta_fields = [getattr(srv, a, None) for a in ("name", "title", "version", "description", "instructions")] if srv else []
    rep.score("B2", "Server name/title/version/description/instructions", 3 * sum(1 for m in meta_fields if m) / 5, 3)

    if tools:
        n = len(tools)
        desc_ok = sum(1 for t in tools if t.description and len(t.description) >= 60)
        rep.score("B3", "Tool descriptions >= 60 chars", round(4 * desc_ok / n, 2), 4)
        params_total = params_ok = constrained = 0
        undocumented_nested = []
        for t in tools:
            # Nested input models ($defs) count too: a list[Model] parameter must document every field (since v1.1)
            nested = []
            for model_name, model in (t.input_schema.get("$defs") or t.input_schema.get("definitions") or {}).items():
                for fname, fspec in (model.get("properties") or {}).items():
                    nested.append((f"{t.name}.{model_name}.{fname}", fspec))
            for qual, fspec in nested:
                if not fspec.get("description"):
                    undocumented_nested.append(qual)
            for _, spec in list(t.input_schema.get("properties", {}).items()) + [(q, f) for q, f in nested]:
                if spec.get("type") == "boolean":  # needs a description, cannot be range-constrained
                    params_total += 1
                    params_ok += bool(spec.get("description"))
                    constrained += 1
                    continue
                params_total += 1
                params_ok += bool(spec.get("description"))
                flat = json.dumps(spec)
                constrained += any(k in flat for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                                                       "minLength", "maxLength", "enum", "minItems", "maxItems", "const"))
        frac = (params_ok / params_total * 0.6 + constrained / params_total * 0.4) if params_total else 1
        rep.score("B4", "Params (incl. nested model fields) described and constrained", round(5 * frac, 2), 5,
                  f"{params_ok}/{params_total} described, {constrained}/{params_total} constrained"
                  + (f"; undocumented nested: {', '.join(undocumented_nested[:5])}" if undocumented_nested else ""))
        rep.score("B5", "outputSchema on every tool", round(4 * sum(1 for t in tools if t.output_schema) / n, 2), 4)
        ann_ok = sum(1 for t in tools if t.annotations and None not in (
            t.annotations.read_only_hint, t.annotations.destructive_hint, t.annotations.idempotent_hint, t.annotations.open_world_hint))
        rep.score("B6", "All four annotations on every tool", round(4 * ann_ok / n, 2), 4)
    src_txt = "\n".join(p.read_text() for p in (server_dir / "src").rglob("*.py"))
    rep.score("B7", "stdio + stateless Streamable HTTP", 2 if ("streamable-http" in src_txt and "stateless_http=True" in src_txt) else 1, 2)

    # ---------------- C. automatic parts
    has_timeout = ("timeout" in src_txt) if re.search(r"httpx|requests|urllib|aiohttp|fetch\(", src_txt) else True
    rep.score("C3", "Network calls have timeouts", 4 if has_timeout else 0, 4)
    rep.score("C4", "Outputs carry warnings for the user", 5 if re.search(r"warning", src_txt) else 0, 5)

    # ---------------- D. automatic parts
    dep_list = py.get("project", {}).get("dependencies", [])
    pinned = all(re.search(r"[<>=~]", d) for d in dep_list)
    rep.score("D3", "Few deps with version ranges", 2 if pinned and len(dep_list) <= 5 else 1, 2, ", ".join(dep_list))

    # ---------------- E. docs
    readme = (server_dir / "README.md").read_text() if (server_dir / "README.md").exists() else ""
    sections = ["痛点", "Tools", "Install", "Try it", "Limitations", "How the numbers work|计算规则|How it works"]
    sec_ok = sum(1 for s in sections if re.search(s, readme))
    bilingual = bool(re.search(r"[\u4e00-\u9fff]", readme)) and bool(re.search(r"[A-Za-z]{4,} [A-Za-z]{4,}", readme))
    rep.score("E1", "Bilingual README with required sections", round(6 * (sec_ok / len(sections)) * (1 if bilingual else 0.5), 2), 6,
              f"{sec_ok}/{len(sections)} sections")
    clients = ["Claude", "Cursor", "VS Code", "Codex"]
    rep.score("E2", "Configs for Claude, Cursor, VS Code, Codex", 3 * sum(c in readme for c in clients) / 4, 3)
    examples = len(re.findall(r"^- 「", readme, flags=re.M))
    rep.score("E3", ">= 5 Chinese example prompts", 3 if examples >= 5 else round(3 * examples / 5, 2), 3, f"{examples} found")
    rep.score("E4", "Has a Prompt or Resource", 3 if (info.get("prompts") or info.get("resources")) else 0, 3)

    # ---------------- F. maintainability
    versions = {py.get("project", {}).get("version"), sjd.get("version"), getattr(srv, "version", None)}
    for pk in sjd.get("packages", []):
        versions.add(pk.get("version"))
    rep.score("F1", "Versions consistent (pyproject, server.json, code)", 3 if len(versions) == 1 and None not in versions else 0, 3,
              str(versions))
    rep.score("F2", "CHANGELOG present", 2 if (server_dir / "CHANGELOG.md").exists() else 0, 2)
    logic_mods = [p for p in (server_dir / "src" / pkg).glob("*.py") if p.name not in {"__init__.py", "__main__.py", "server.py"}]
    rep.score("F3", "Business logic separated from protocol layer", 3 if logic_mods else 0, 3)
    ver = py.get("project", {}).get("version", "")
    name = server_dir.name
    rep.score("F4", "Review report in reports/", 2 if (ROOT / "reports" / f"{name}-{ver}.md").exists() else 0, 2)

    got, mx = rep.totals()
    if as_json:
        print(json.dumps({"gates_ok": rep.gates_ok, "auto_score": got, "auto_max": mx,
                          "rows": [dict(zip(["code", "name", "ok", "got", "max", "detail"], r)) for r in rep.rows]},
                         ensure_ascii=False, indent=2))
    else:
        print(f"\nVic MCP audit · {server_dir.relative_to(ROOT)}\n")
        for code, nm, ok, g, m, d in rep.rows:
            mark = "✅" if ok else "❌"
            pts = "" if code.startswith("G") else f" {g:g}/{m:g}"
            print(f"{mark} {code} {nm}{pts}" + (f"  · {d}" if d else ""))
        print(f"\nHard gates (automated): {'PASS' if rep.gates_ok else 'FAIL'}")
        print(f"Automated score: {got:g} / {mx:g}")
        print("Manual items to confirm in the report: G1, G8, A1-A4, C1, C2, D1, D2, D4 (see REVIEW_STANDARD.md)\n")
    return 0 if rep.gates_ok else 1


if __name__ == "__main__":
    sys.exit(main())
