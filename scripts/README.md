# Developer utilities

Place reproducible environment, import, benchmark, and maintenance utilities here. Utilities should use backend modules rather than duplicate scientific logic and must not alter external source collections by default.

With Rutile running, run `scripts/check_browser.py` using the project’s Python environment. It uses Playwright with Microsoft Edge and the bundled Al–Cu TDB. It covers the animated shell, appearance settings, diagram workflow, and narrow layouts, and saves preview images in `workspace/`.
