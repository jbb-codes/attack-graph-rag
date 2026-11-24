# Python for Node/TS developers

A one-to-one map from what you know to what this repo uses. New rows are added as issues are implemented.

## Node/TS to Python map

| Node/TS                         | Python here                               | Notes                                           |
| ------------------------------- | ----------------------------------------- | ----------------------------------------------- |
| `package.json`                  | `pyproject.toml`                          | Name, deps, scripts, build config.              |
| `package-lock.json`             | `uv.lock`                                 | Exact pinned versions. Commit it.               |
| `npm` / `pnpm`                  | `uv`                                      | Package manager, written in Rust and very fast. |
| `process.env.X`                 | `os.environ` / `env.get("X", "")`       | A dict of env vars; `.get` avoids a `KeyError`. |
| `npm install`                   | `uv sync`                                 | Installs deps from the lockfile.                |
| `node_modules/`                 | `.venv/`                                  | Local installed packages. Gitignored.           |
| `npm run x` / `npx x`           | `uv run x`                                | Runs inside `.venv`.                            |
| `"bin"` in package.json         | `[project.scripts]`                       | Gives you the `attack-graph` command.           |
| `devDependencies`               | `[dependency-groups] dev`                 | Test-only deps.                                 |
| `vitest` / `jest`               | `pytest`                                  | Test files are named `test_*.py`.               |
| `tsconfig` + `tsc` build        | `hatchling`                               | Packaging tool, only used when building.        |
| `interface` / `type`            | `@dataclass(frozen=True)`                 | A plain data shape. `frozen` means read-only.   |
| `process.argv` + commander      | `argparse`                                | Built in. Parses CLI args.                      |
| `process.exit(1)`               | `return 1` from `main()`                  | The exit code is how scripts signal failure.    |
| `console.log` / `console.error` | `print()` / `print(..., file=sys.stderr)` | stdout vs stderr.                               |
| `import { x } from "./y"`       | `from attack_graph.y import x`            | `__init__.py` marks a folder as a package.      |
| `string \| null`                | `str \| None`                             | Same idea.                                      |
| `fetch(url)` / `https.get`      | `urllib.request.urlopen(url)`             | Built in. No dependency needed.                 |
| `crypto.createHash("sha256")`   | `hashlib.sha256(data).hexdigest()`        | Built in.                                       |
| `fs.rename` (atomic swap)       | `os.replace(tmp, target)`                 | Overwrites the target in one step.              |
| `path.join` / `fs.existsSync`   | `Path("a") / "b"`, `path.exists()`        | `pathlib.Path` does both.                       |
| `process.chdir` in a test       | `monkeypatch.chdir(tmp_path)`             | pytest undoes it after each test.               |
| `beforeEach` (shared setup)     | `@pytest.fixture` (in `conftest.py`)      | `autouse=True` applies it to every test.        |
| `interface Store { ... }`       | `class VectorStore(Protocol)`             | Any class with those methods fits.              |
| Vector DB client (Pinecone etc) | `chromadb.PersistentClient(path=...)`     | Local, stored in a folder.                      |
| `test.each([...])`              | `@pytest.mark.parametrize("x", [...])`    | Runs the test once per value.                   |
| `expect(fn).toThrow(/msg/)`     | `with pytest.raises(Err, match="msg")`    | `match` is a regex on the message.              |
| `describe.skip` / tags          | `@pytest.mark.model` + `markers` config   | Custom label; select with `-m model`.           |

## Syntax you'll trip on

- Indentation is the braces. There are no `{}` for blocks.
- `def f(x: str) -> int:` is a typed function. Types are hints only and aren't enforced at runtime.
- `self` is `this`, and it's an explicit first parameter in methods.
- `_name` with a leading underscore means private by convention.
- `@classmethod` is like a `static` factory method, here `AttackGraph.from_stix_file(...)`.
- `tuple` is a fixed-size array and `set` is a unique-value `Set`.
- `with ... as x:` is like try/finally. It cleans up when the block ends.
- `f"hi {name}"` is a template literal.
- `raise X from exc` is `throw`, keeping the original error as the cause.
- `def main(argv, *, fetch=http_fetch)`: the bare `*` makes everything after it keyword-only, like passing an options object.
- A default argument like `fetch=http_fetch` is the real thing; tests pass a fake.
- `Callable[[str], bytes]` is a function type, like `(url: string) => Buffer`.
- `@property` makes a method read like a field, like a TS `get` accessor.
- `except (A, B) as exc:` catches either error type.
- `Protocol` is a structural interface, like a TS `interface`: no `implements`, matching methods is enough.
- `def f(x, limit: int = 5)`: default values work like TS default params.
- `zip(a, b, strict=True)` walks lists side by side and errors if lengths differ.
- `[f(x) for x in xs]` is `xs.map(f)`. `sorted(xs, key=...)` is `sort` with a key.
- `from x import y` inside a function delays a slow import until it is needed.
- `result["ids"][0]`: Chroma returns one list per question, so `[0]` picks ours.
- `Literal["a", "b"]` is a string-union type, like `"a" | "b"` in TS.
- `@dataclass(frozen=True)` is a read-only object with a constructor made for you, like a `readonly` interface plus factory.
- `str | None` is `string | null`. `llm or OfflineLLM()` picks the fallback when `llm` is `None`.
- `re.compile(r"...")` is a `RegExp`. `findall` returns every match as a list.
- `dict.fromkeys(items)` removes duplicates and keeps order, like `[...new Set(items)]`.
- `(x for x in xs if cond)` is a lazy generator, like a chained iterator; `"".join(...)` consumes it.
- `@pytest.mark.parametrize("q", [...])` runs one test per value, like `it.each`.
- `pytest.raises(Err)` is `expect(() => ...).toThrow(Err)`.
- `x in {"a", "b"}` is a quick set membership check, like `set.has(x)`.
- `os.environ` is a dict, so use `env.get("X", "default")`. `os.environ["X"]` raises `KeyError` if missing.
- `Mapping[str, str]` is a read-only dict type. Taking it as a parameter lets tests pass a plain dict.
- `field(default="", repr=False)` is a dataclass field that stays out of printed output, so secrets don't leak.
- `raise X(...) from None` throws a new error and hides the original, so its message can't leak.
- `except Exception:` is `catch (e)`. Prefer naming the type when you can.
- `"".join(parts)` glues strings, like `parts.join("")`.
- `Callable[[str, dict], dict]` is a function type, like `(url: string, body: object) => object`.
- `@pytest.mark.live` tags a test; `-m 'not live'` in `addopts` skips tagged tests by default.
- `urllib.request` is the standard-library HTTP client. Think a tiny built-in `fetch`.
- `FastAPI()` is `express()`. `@app.get("/x")` and `@app.post("/x")` register routes, like `app.get("/x", handler)`.
- `async def` handlers use `await`, as in JS. `run_in_threadpool(fn, arg)` runs blocking code off the event loop.
- `TestClient(app)` calls routes in memory, like `supertest(app)`. `client.post("/x", json={...})`.
- `JSONResponse(body, status_code=400, headers={...})` is `res.status(400).json(body)`.
- `@app.middleware("http")` wraps every request, like Express `app.use`. `await call_next(request)` is `next()`.
- `deque` is a queue with fast pushes and pops at both ends. `popleft()` is `shift()`.
- `time.monotonic` is a clock that never jumps backwards; use it to measure durations, not dates.
- `isinstance(x, str)` is `typeof x === "string"`. `json.loads` is `JSON.parse` and raises `ValueError` on bad input.
- `lambda: expr` is `() => expr`. A `Callable[[], float]` type is `() => number`.
- `@pytest.fixture` returning a function makes a test factory; tests take it as a parameter by name.
- `caplog` is a pytest fixture holding captured log lines, for asserting what was (not) logged.
- `logging.getLogger(name)` then `log.warning("x %s", v)` logs lazily, like a leveled `console`.
- `str.replace` is `String.replaceAll` with plain text: `s.replace("<", "&lt;")` changes every match.
- `re.sub(pattern, " ", s)` is `s.replace(/pattern/g, " ")`. `" ".join(s.split())` collapses whitespace runs.
- `if len(x := f(y)) >= 25` is the walrus operator: assign and use a value in one expression.
- `any(rule in text for rule in rules)` is `rules.some(r => text.includes(r))`.
- `pytest.param(value, id="name")` names one case of `@pytest.mark.parametrize`, like a test title in `it.each`.
- `Path(__file__).parent` is the folder of this file, like `__dirname`. `.read_text()` reads it as a string.
- A module-level `assert` inside a helper (`assert len(found) == 1, "message"`) fails the calling test with that message.
