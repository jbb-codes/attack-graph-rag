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
