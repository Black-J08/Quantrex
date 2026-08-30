# Quantrex — Agent Instructions

## Project Overview
**Quantrex** is a Python-based event-driven algorithmic trading framework for quantitative researchers.

**Core Goal:** A researcher writes **one simple Python strategy script** and uses the **exact same script** for backtesting, paper/mock trading, and live trading.

**Design Philosophy:**
- Hide infrastructure complexity behind a simple researcher-facing API
- Researcher mainly defines strategy logic and reacts to market events
- Make the **easy path the default** while keeping the underlying architecture robust and fast enough for large-scale backtests and real-time trading
- Complexity lives inside the framework, not inside the strategy script


## Pillars of Implementation
Every solution you propose or implement must be vetted through the search tools to ensure it meets the following four pillars:

* **Robustness:** Strong error handling, type safety, input validation, and self-healing capabilities.
* **Redundancy:** High availability, failover mechanisms, no single points of failure (SPOFs), and data replication.
* **Scalability:** Horizontal scaling capabilities, stateless design patterns, and efficient resource utilization.
* **High Performance:** Optimized data structures, caching strategies, low-latency communication protocols, and minimized I/O bottlenecks.

## Search Workflow
1. **Query Formulation:** Use specific queries combining your target technology with keywords like `"production ready"`, `"error handling best practices"`, `"scalability best practices"`, `"performance optimization"`, `"caching strategy"` or `"industry standard"`.
2. **Tool Execution:** Call relevant MCP tool or available skills.
3. **Synthesis:** Incorporate the discovered patterns directly into your response or code generation.
4. **Citation:** Briefly note which standard or documentation source informed your design choice.

## Logging & Error Tracking Standards

Use the standard library [`logging`](https://docs.python.org/3/library/logging.html) module via the `quantrex_core.logging` facade: `get_logger(name)` for module-scoped loggers, `setup_logging(level, log_file)` at the process entry point. Importing `quantrex_core.logging` has no side effects.

### Severity Levels
Use the standard levels.

| Level | When to use |
|---|---|
| **DEBUG (10)** | Diagnostic information for developers. |
| **INFO (20)** | Standard operational events and positive confirmations of completed work. |
| **WARNING (30)** | Non-critical issues or potential anomalies. |
| **ERROR (40)** | Errors that prevent an operation from completing with exc_info=True always. |
| **CRITICAL (50)** | System-breaking failures requiring immediate attention. |

### Format
* Use lazy `%`-formatting: `logger.info("foo %s", x)` — never f-strings at the call site.
* Pass values as arguments, not pre-formatted strings, so the formatting cost is only paid when the record is actually emitted.

### Exception Handling Rules
* **Never swallow exceptions silently.**
* When catching exceptions, **always** use `logger.exception(..., exc_info=True)` (or `logger.error(..., exc_info=True)`). This guarantees the full stack trace, error context, and line numbers are captured.

## Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
* State your assumptions explicitly. If uncertain, ask.
* If multiple interpretations exist, present them - don't pick silently.
* If a simpler approach exists, say so. Push back when warranted.
* If something is unclear, stop. Name what's confusing. Ask.

## Object-Oriented Design

* Follow core OOP principles consistently in Python: **encapsulation, abstraction, composition, polymorphism, and single responsibility**.
* Model real-world/domain entities as cohesive classes that encapsulate both their state and the behavior operating on that state.
* Prefer **composition and dependency injection** over inheritance when establishing relationships between components.
* Keep classes focused, modular, reusable, and independently testable; avoid god classes and unnecessary coupling.
* Use `Protocol` only to define genuine behavioral contracts or replaceable dependencies—not merely because two classes interact.
* Expose behavior through well-defined public interfaces and keep implementation details private.
* Before introducing an abstraction, verify that it represents a real domain responsibility or architectural boundary; avoid speculative abstractions.

## Simplicity First
**Minimum code that solves the problem. Nothing speculative.**

* No features beyond what was asked.
* No abstractions for single-use code.
* No "flexibility" or "configurability" that wasn't requested.
* No error handling for impossible scenarios.
* Avoid backwards compatibility unless explicitly requested.
* If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## Surgical Changes
**Touch only what you must. Clean up only your own mess.**

When editing existing code:
* Don't "improve" adjacent code, comments, or formatting.
* Don't refactor things that aren't broken.
* Match existing style, even if you'd do it differently.
* If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
* Remove imports/variables/functions that YOUR changes made unused.
* Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## Dependency Architecture

* Eliminate circular dependencies through proper architecture; never use workarounds such as typing.TYPE_CHECKING, deferred imports, local imports, or lazy imports solely to break circular imports.
* Prefer architectural separation, dependency inversion, shared core modules, and protocols/interfaces where appropriate.

## Type Hinting

* **Never** use string-based forward references.
* Never use `from __future__ import annotations` solely to work around circular dependencies.
* Structure modules so annotations resolve naturally without deferred evaluation.
* Use `typing.Self` where appropriate for class methods.

## Naming, Module Organization & Responsibility

Adhere to widely accepted software engineering principles (e.g. SOLID, Clean Architecture, Domain-Driven Design where appropriate, and the Python packaging recommendations from the Python ecosystem). Organize code so that each file, class, and function has a single, well-defined responsibility.

## Monorepo & Python Packaging (uv + pyproject.toml)

**Use `uv` for everything: dependency resolution, virtual environments, and building.** Never use `python`, `python3`, `pip`, or manually activate venvs. Run scripts with `uv run python <script.py>` and tests with `uv run --package <name> pytest packages/<name>/tests`. Set up or refresh the environment with `uv sync` (the root declares `default-groups = ["dev"]`, so dev tools install automatically). Dependencies live in `pyproject.toml`; versions are pinned in `uv.lock`.

**Build backend:** every package uses `uv_build` (`build-backend = "uv_build"`). `uv_build` defaults `module_root` to `src/`, so no `[tool.setuptools.packages.find]` is needed. Do not introduce `setuptools`, `hatchling`, or any other backend.

**Workspace:** the root `pyproject.toml` is a virtual workspace root (no `[project]` table). It declares `[tool.uv.workspace] members = ["packages/*"]`, `[tool.uv.sources]` with `{ workspace = true }` for every member (inherited by all members — do not redeclare sources per member), and `[dependency-groups] dev` (PEP 735) for pytest, pytest-cov, and any other dev tooling. Do not add `[project.optional-dependencies]` for dev tools; extras are reserved for opt-in feature flags.

**Per member:** each member's `pyproject.toml` contains only `[project]` (with `requires-python`) and `[build-system]` (with `uv_build`). Cross-member dependencies are listed as bare names in `[project] dependencies` and resolved via the root's `[tool.uv.sources]`. Pin the interpreter at the workspace root with `.python-version`.

**Not allowed (deprecated):** `uv sync --dev`, `[project.optional-dependencies] dev`, `[tool.uv.dev-dependencies]`, `[tool.setuptools.packages.find]`, per-member `[tool.uv.sources]`, any non-`uv_build` build backend, manual venv activation.


### Monorepo Layout
```
quantrex/
├── packages/
│   ├── core/               # quantrex-core
│   │   ├── src/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── data/               # quantrex-data
│   │   ├── src/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── backtest/           # quantrex-backtest
│   │   ├── src/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── live/               # quantrex-live
│   │   ├── src/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── test-support/       # quantrex-test-support
│       ├── src/
│       ├── tests/
│       ├── pyproject.toml
│       └── README.md
├── pyproject.toml          # virtual workspace root
├── uv.lock                 # single lockfile for all
├── .python-version         # workspace-wide Python pin
├── .gitignore
├── AGENTS.md
└── README.md
```
