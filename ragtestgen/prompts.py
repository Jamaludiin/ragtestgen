"""Prompt construction and response parsing for RAGTestGen."""
import re

SYSTEM = (
    "You are an expert Java unit-testing engineer. You write JUnit 5 tests that "
    "compile and run against the exact source you are given. You never invent "
    "methods, fields or classes that are not present in that source. You follow "
    "the required output format exactly."
)

CATEGORIES = ["typical", "boundary", "error", "special"]

TEMPLATE = """\
Generate JUnit 5 unit tests for the Java methods listed below.

## Retrieved context from the program under test
{context}

## Full source of the classes under test
```java
{sources}
```

## Target methods
{targets}

## Output format — follow exactly, no prose outside the blocks
For every test case emit one block:

<<<TEST>>>
METHOD: <exact name of the target method this test exercises>
CATEGORY: <one of: typical | boundary | error | special>
DESC: <one short line describing the scenario>
```java
@Test
public void testMethodName_Scenario_ExpectedOutcome() throws Exception {{
    // test body
}}
```
<<<END>>>

## Rules
1. For EACH target method emit exactly {per_method} test cases, one per
   category, in this order:
   - typical: ordinary inputs and expected behaviour
   - boundary: minimum, maximum, empty, zero, null, or limit values
   - error: inputs that should raise or that exercise failure handling
   - special: logic specific to this method (branches, state, concurrency)
   If a category genuinely does not apply to a method, still emit the block and
   use the nearest applicable scenario rather than skipping it.
2. Emit ONLY test methods. No imports, no package line, no class declaration,
   no @BeforeEach or fields. The harness supplies those.
3. The test class is generated into package `{package}`, so package-private and
   protected members of the classes under test are directly accessible. Do not
   use reflection for them.
4. Use reflection ONLY for members declared `private`:
   java.lang.reflect.Method m = Cls.class.getDeclaredMethod("n", int.class);
   m.setAccessible(true);
   Object r = m.invoke(instance, 1);
   Fields likewise via getDeclaredField.
5. Assertions come from org.junit.jupiter.api.Assertions and are already
   statically imported: assertEquals, assertTrue, assertThrows, assertNull, etc.
   For doubles always pass a delta: assertEquals(1.0, x, 1e-9).
6. Every test method needs a UNIQUE name across the whole response, and must
   declare `throws Exception`.
7. Construct objects only with constructors that exist in the source above.
8. Do not test `main`. Do not start threads that may not terminate; if a method
   starts a thread, join it with a timeout.
9. Never write a test that reads System.in, sleeps more than 100 ms, or loops
   unboundedly.

Do not explain your reasoning. Emit the {n_expected} blocks now, nothing else.
"""

BLOCK = re.compile(
    r"<<<TEST>>>(?P<body>.*?)(?:<<<END>>>|(?=<<<TEST>>>)|\Z)",
    re.DOTALL)
FIELD = {k: re.compile(rf"^\s*{k}\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
         for k in ("METHOD", "CATEGORY", "DESC")}
CODE = re.compile(r"```(?:java)?\s*\n(?P<code>.*?)```", re.DOTALL)
BARE_TEST = re.compile(r"(@Test\b.*?)(?=\n\s*@Test\b|\Z)", re.DOTALL)


def build(context, sources, targets, package, per_method=len(CATEGORIES)):
    tgt = "\n".join(
        f"- {m['class']}.{m['name']}({', '.join(m['params'])}) "
        f"[visibility={m['visibility']}, cyclomatic_complexity={m['complexity']}"
        f"{', constructor' if m['constructor'] else ''}"
        f"{', static' if m['static'] else ''}]"
        for m in targets)
    return TEMPLATE.format(context=context.strip() or "(none retrieved)",
                           sources=sources, targets=tgt,
                           package=package or "(default package)",
                           per_method=per_method,
                           n_expected=per_method * len(targets))


def _clean(code):
    """Strip anything the model was told not to emit."""
    out = []
    for line in code.splitlines():
        s = line.strip()
        if s.startswith(("import ", "package ")):
            continue
        out.append(line)
    code = "\n".join(out).strip()
    # unwrap a stray class declaration
    m = re.match(r"^(?:public\s+)?class\s+\w+\s*\{(.*)\}\s*$", code, re.DOTALL)
    if m:
        code = m.group(1).strip()
    return code


def parse(response):
    """Parse a model response into test records.

    Returns (tests, stats). Falls back to bare @Test scraping when the model
    ignores the block format, so that format violations degrade rather than
    zeroing the run.
    """
    tests, seen = [], set()
    blocks = list(BLOCK.finditer(response))
    for i, b in enumerate(blocks):
        body = b.group("body")
        cm = CODE.search(body)
        if not cm:
            continue
        code = _clean(cm.group("code"))
        if "@Test" not in code or not code:
            continue
        def f(k, default=""):
            mm = FIELD[k].search(body)
            return mm.group(1).strip() if mm else default
        cat = f("CATEGORY", "unspecified").lower().split()[0] if f("CATEGORY") else "unspecified"
        rec = {"seq": i + 1, "method": f("METHOD", "?"),
               "category": cat if cat in CATEGORIES else "unspecified",
               "description": f("DESC", ""), "code": code, "parsed_by": "block"}
        tests.append(rec)
    fallback = False
    if not tests:
        fallback = True
        for cm in CODE.finditer(response):
            for bm in BARE_TEST.finditer(cm.group("code")):
                code = _clean(bm.group(1))
                if "@Test" in code:
                    tests.append({"seq": len(tests) + 1, "method": "?",
                                  "category": "unspecified", "description": "",
                                  "code": code, "parsed_by": "fallback"})
    # de-duplicate by test method name
    uniq = []
    for t in tests:
        nm = re.search(r"(?:void|public|private|protected|\s)\s*(\w+)\s*\(", t["code"])
        name = nm.group(1) if nm else f"test_{t['seq']}"
        if name in seen:
            continue
        seen.add(name)
        t["test_name"] = name
        uniq.append(t)
    stats = {"blocks_found": len(blocks), "tests_parsed": len(uniq),
             "format_compliant": not fallback and len(uniq) > 0,
             "used_fallback": fallback and len(uniq) > 0}
    return uniq, stats
