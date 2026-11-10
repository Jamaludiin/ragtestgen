"""End-to-end RAGTestGen pipeline: index, retrieve, generate, compile, measure."""
import json, re, threading, time
from collections import Counter
from pathlib import Path

from . import harness, prompts
from .analyze import analyze, testable
from .llm import chat, LLMError, PayloadTooLarge
from .retrieval import CodeIndex

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "bench"
RUNS = ROOT / "runs"

MAX_TARGETS = 15          # cap on target methods per program
TESTS_PER_METHOD = 4      # one per category: typical, boundary, error, special
BATCH = 4                 # target methods per LLM request
# Groq's free tier allows 7000 input tokens/minute; ~4 chars/token leaves room
# for the response and for a second request inside the same window.
PROMPT_BUDGET = 20000     # characters


def load_program(name):
    d = BENCH / name
    src = d / "src"
    files = sorted(src.rglob("*.java"))
    all_methods = analyze(files)
    methods = testable(all_methods)
    # primary package = the one declaring the most target methods
    pkgs = Counter(m["package"] for m in methods)
    package = pkgs.most_common(1)[0][0] if pkgs else ""
    return {"name": name, "dir": d, "src": src, "files": files,
            "classes": d / "classes", "methods": methods,
            "all_methods": all_methods, "package": package,
            "randoop": sorted((d / "randoop").glob("*.java")) if (d / "randoop").exists() else []}


def select_targets(methods, cap=MAX_TARGETS):
    """All testable methods, or the `cap` most complex when there are more.

    Deterministic: sorted by descending cyclomatic complexity, then class, then
    name, so the selection is reproducible and independent of file order.
    """
    ordered = sorted(methods, key=lambda m: (-m["complexity"], m["class"], m["name"]))
    return sorted(ordered[:cap], key=lambda m: (m["class"], m["startLine"]))


_INDEX_LOCK = threading.Lock()


def get_index(prog):
    """Build the retrieval index once per program and reuse it.

    Embedding is the dominant non-LLM cost, and the corpus is the program's own
    sources, so the index is identical for every model and every batch. The lock
    keeps concurrent model runs on one program from building it twice.
    """
    with _INDEX_LOCK:
        if prog.get("_index") is None:
            index = CodeIndex()
            for f in prog["files"]:
                index.add_file(f.name, f.read_text(errors="replace"))
            prog["_index"] = index
        return prog["_index"]


def elide_bodies(text, methods, keep):
    """Return `text` with the bodies of methods outside `keep` replaced.

    Signatures, fields and class structure survive, so the model still sees every
    constructor and method it may call; only implementation detail it does not
    need for the targets at hand is dropped.
    """
    lines = text.splitlines()
    spans = sorted(((m["startLine"] - 1, m["endLine"] - 1) for m in methods
                    if (m["class"], m["name"], m["startLine"]) not in keep
                    and m["endLine"] > m["startLine"] and m["endLine"] <= len(lines)),
                   key=lambda s: s[0])
    out, i, last_end = [], 0, -1
    for s, e in spans:
        if s <= last_end or s < i:       # nested or overlapping: leave intact
            continue
        out.extend(lines[i:s])
        block = "\n".join(lines[s:e + 1])
        head, brace, _ = block.partition("{")
        out.append(f"{head}{{ /* body elided */ }}" if brace else block)
        i, last_end = e + 1, e
    out.extend(lines[i:])
    return "\n".join(out)


def build_prompt(prog, targets, per_method=TESTS_PER_METHOD, budget=PROMPT_BUDGET):
    index = get_index(prog)
    query = "\n".join(m["body"] for m in targets)
    context, n_chunks = index.retrieve(query)
    # full sources of the classes that declare the targets
    want = {m["file"] for m in targets}
    files = [f for f in prog["files"]
             if any(str(f) == w or Path(w).name == f.name for w in want)]
    texts = {f: f.read_text(errors="replace") for f in files}

    def assemble(ctx, tx):
        sources = "\n\n".join(f"// ==== {f.name} ====\n{tx[f]}" for f in files)
        return prompts.build(ctx, sources, targets, prog["package"], per_method)

    user = assemble(context, texts)
    # Free-tier providers reject a prompt over their per-minute input budget, so
    # an oversized one is degraded rather than lost: retrieved context goes
    # first, then the bodies of methods that are not targets.
    elided = trimmed = False
    if len(user) > budget:
        trimmed = True
        user = assemble("", texts)
    if len(user) > budget:
        elided = True
        keep = {(m["class"], m["name"], m["startLine"]) for m in targets}
        by_file = {}
        for m in prog.get("all_methods", []):
            by_file.setdefault(Path(m["file"]).name, []).append(m)
        texts = {f: elide_bodies(t, by_file.get(f.name, []), keep)
                 for f, t in texts.items()}
        user = assemble("", texts)
    return user, {"retrieved_chunks": 0 if trimmed else n_chunks,
                  "index_chunks": index.n_chunks,
                  "context_chars": 0 if trimmed else len(context),
                  "prompt_chars": len(user),
                  "context_dropped": trimmed, "bodies_elided": elided}


def generate(prog, model_cfg, targets, per_method=TESTS_PER_METHOD, temperature=0.2,
             batch=BATCH):
    """Generate a suite for `targets`, in batches of `batch` methods per request.

    Asking one request to cover every target at once makes the response long
    and fragile: a single truncation loses the whole suite. Batching bounds each
    response and lets a failed batch cost only its own methods.
    """
    t0 = time.time()
    batch = model_cfg.get("batch") or batch
    queue = [targets[i:i + batch] for i in range(0, len(targets), batch)]
    tests, batches, raws = [], [], []
    gi = 0
    while queue:
        grp = queue.pop(0)
        gi += 1
        user, pmeta = build_prompt(prog, grp, per_method)
        b = {"batch": gi, "n_targets": len(grp),
             "targets": [f"{m['class']}.{m['name']}" for m in grp],
             "expected_tests": len(grp) * per_method, **pmeta}
        try:
            raw, meta = chat(model_cfg["provider"], model_cfg["model"], prompts.SYSTEM, user,
                             temperature=temperature,
                             max_tokens=model_cfg.get("max_tokens", 16000),
                             reasoning_effort=model_cfg.get("reasoning_effort", "low"))
        except PayloadTooLarge as e:
            # Over the model's budget: halve the batch and try the pieces. A
            # single method that is still too large is genuinely untestable here.
            if len(grp) > 1:
                h = len(grp) // 2
                queue[:0] = [grp[:h], grp[h:]]
                gi -= 1
                continue
            b.update({"ok": False, "error": f"too large: {e}"[:300], "tests_parsed": 0,
                      "split": True})
            batches.append(b)
            continue
        except LLMError as e:
            b.update({"ok": False, "error": str(e), "tests_parsed": 0})
            batches.append(b)
            continue
        parsed, pstats = prompts.parse(raw)
        raws.append(f"// ===== batch {gi}: {', '.join(b['targets'])} =====\n{raw}")
        b.update({"ok": True, "error": None, "tests_parsed": len(parsed), **pstats,
                  "latency_s": meta["latency_s"], "finish_reason": meta["finish_reason"],
                  "reasoning_tokens": meta.get("reasoning_tokens"),
                  "completion_tokens": meta.get("usage", {}).get("completion_tokens")})
        batches.append(b)
        tests.extend(parsed)

    # Test-method names must be unique across the whole assembled class. Batches
    # are generated independently, so collisions between them are expected; the
    # declaration in the code is renamed too, since tests are selected by name.
    seen = set()
    for t in tests:
        orig = t["test_name"]
        nm, i = orig, 2
        while nm in seen:
            nm = f"{orig}_b{i}"; i += 1
        seen.add(nm)
        if nm != orig:
            t["code"] = re.sub(rf"\b{re.escape(orig)}\b(?=\s*\()", nm, t["code"], count=1)
            t["test_name"] = nm
    for i, t in enumerate(tests, 1):
        t["id"] = i

    ok_batches = [b for b in batches if b.get("ok")]
    expected = sum(b["expected_tests"] for b in batches)
    return {"ok": len(tests) > 0,
            "error": None if tests else "; ".join(
                b.get("error", "no tests parsed") for b in batches)[:400],
            "raw": "\n\n".join(raws), "tests": tests, "batches": batches,
            "parse": {"expected_tests": expected, "tests_parsed": len(tests),
                      "yield": round(len(tests) / expected, 3) if expected else 0.0,
                      "batches_ok": len(ok_batches), "batches_total": len(batches),
                      "format_compliant": all(b.get("format_compliant") for b in ok_batches)
                                          if ok_batches else False},
            "llm_meta": {"total_latency_s": round(sum(b.get("latency_s", 0) for b in batches), 2),
                         "completion_tokens": sum(b.get("completion_tokens") or 0 for b in batches),
                         "reasoning_tokens": sum(b.get("reasoning_tokens") or 0 for b in batches)},
            "wall_s": round(time.time() - t0, 2)}


def evaluate(prog, model_key, gen, workdir):
    """Compile, execute and measure a generated suite."""
    workdir.mkdir(parents=True, exist_ok=True)
    cls = f"RagTest_{re.sub(r'[^A-Za-z0-9]', '', model_key)}_{re.sub(r'[^A-Za-z0-9]', '', prog['name'])}"
    kept, dropped, tclasses, log = harness.compile_suite(
        workdir, prog["package"], cls, gen["tests"], prog["classes"])
    fqcn = f"{prog['package']}.{cls}" if prog["package"] else cls
    res = harness.run_tests(fqcn, kept, prog["classes"], tclasses, workdir / "exec") if kept else []
    execs = [workdir / "exec" / r["exec"] for r in res]
    cov = harness.coverage(prog["classes"], execs) if execs else {}
    merged = harness.merge_exec(execs, workdir / "suite.exec")
    suite = harness.coverage(prog["classes"], [merged])[merged.name] if merged else {}
    for r in res:
        c = cov.get(r["exec"], {})
        r["instr_covered"] = c.get("instr_covered", 0)
        r["line_covered"] = c.get("line_covered", 0)
        r["branch_covered"] = c.get("branch_covered", 0)
        r["covered_lines"] = c.get("lines", {})
        r.pop("output", None) if r["status"] == "pass" else None
    return {"compile_log": log, "kept": len(kept), "dropped": dropped,
            "results": res, "suite": suite, "test_class": fqcn}


def total(suite, key):
    return suite.get(f"{key}_covered", 0) + suite.get(f"{key}_missed", 0)


def pct(suite, key):
    t = total(suite, key)
    return round(100 * suite.get(f"{key}_covered", 0) / t, 2) if t else 0.0
