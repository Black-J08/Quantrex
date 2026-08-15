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
You must implement structured logging across all codebases using `loguru`-compliant severity levels and strict exception-tracking rules.

### Severity Levels
Always assume the `loguru` Python library for logging. Align all application logging strictly to these semantic levels:
* **TRACE (5):** Granular, step-by-step execution details.
* **DEBUG (10):** Diagnostic information for developers.
* **INFO (20):** Standard operational events.
* **SUCCESS (25):** Positive confirmation of completed operations.
* **WARNING (30):** Non-critical issues or potential anomalies.
* **CRITICAL (50):** System-breaking failures requiring immediate attention.

### Exception Handling Rules
* **Never swallow exceptions silently.** * When catching exceptions, **always** use `.exception()` (or the local equivalent that forces `exc_info=True`). This guarantees that the entire stack trace, error context, and line numbers are captured in the log output for rapid debugging.

## Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
* State your assumptions explicitly. If uncertain, ask.
* If multiple interpretations exist, present them - don't pick silently.
* If a simpler approach exists, say so. Push back when warranted.
* If something is unclear, stop. Name what's confusing. Ask.

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

**Use `uv` for all Python package management.** It is the single tool for dependency resolution, virtual environments, and building. Use `uv` exclusively for Python execution and testing. Run Python scripts with `uv run python <script.py>` and run pytest with `uv run pytest`. Do not use `python`, `python3`, `pip`, or manually activate virtual environments. Ensure dependencies are managed through the project's `pyproject.toml` and `uv.lock`.


### Monorepo Layout (example)
```
quantrex/
├── packages/
│   ├── core/               # quantrex-core
│   │   ├── src/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── backtest/           # quantrex-backtest
│   │   ├── src/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── live/               # quantrex-live
│       ├── src/
│       ├── tests/
│       ├── pyproject.toml
│       └── README.md
├── pyproject.toml          # root workspace config
├── uv.lock                 # single lockfile for all
├── .gitignore
├── AGENTS.md
└── README.md
```
