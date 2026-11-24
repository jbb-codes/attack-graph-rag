# Python for Node/TS developers

A one-to-one map from what you know to what this repo uses. New rows are added as issues are implemented.

## Node/TS to Python map

| Node/TS                         | Python here                               | Notes                                           |
| ------------------------------- | ----------------------------------------- | ----------------------------------------------- |
| `package.json`                  | `pyproject.toml`                          | Name, deps, scripts, build config.              |
| `package-lock.json`             | `uv.lock`                                 | Exact pinned versions. Commit it.               |
| `npm` / `pnpm`                  | `uv`                                      | Package manager, written in Rust and very fast. |
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
