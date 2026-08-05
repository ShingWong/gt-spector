# Console Lightweight Selection Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bot selection in the console tree instant by having `_on_tree_select` update only the `☑/☐` checkbox column, instead of running the full heavy `_update_rows` (~1.5-2s under load).

**Architecture:** `_on_tree_select` calls a new lightweight `_update_selection_only()` that re-renders only the selection glyph (`sel` column, the `☑/☐` at index 0 of each row's values) for the currently selected bots. The full `_update_rows` continues on the 2s `_poll` and after actions.

**Tech Stack:** Python, tkinter Treeview, `viewer/bot_console.py`.

## Global Constraints

- `_on_tree_select` must NOT call `_update_rows()`. It calls `_update_selection_only()` instead.
- `_update_selection_only()` updates only the `sel` column (index 0 of each row's values) — reading `self._tree.selection()` and rewriting `self._tree.item(bot.name, values=(...))` with the current values but a fresh `☑/☐`.
- The full `_update_rows` remains for `_poll` (2s), `_build_rows`, `_action`, `_action_all`.
- Existing tests must pass.

---
### Task 1: Lightweight selection update

**Files:**
- Modify: `viewer/bot_console.py` (`_on_tree_select`, add `_update_selection_only`)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `self._tree` (`.selection()`, `.item()`), `self._manager.bots`.
- Produces: `_update_selection_only() -> None` — cheap checkbox re-render; `_on_tree_select` calls it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_on_tree_select_does_not_call_update_rows():
    c = make_console()
    calls = []
    c._update_rows = lambda: calls.append("rows")
    c._update_selection_only = lambda: calls.append("sel")
    c._on_tree_select()
    assert calls == ["sel"]  # must NOT call the full update_rows


def test_update_selection_only_rewrites_sel_column():
    c = make_console()
    rows = {}

    class FakeTree:
        def selection(self):
            return ("bot02",)

        def item(self, iid, values=None, **kw):
            if values is not None:
                rows[iid] = list(values)
            return rows.get(iid)

    c._tree = FakeTree()
    # seed two rows
    rows["bot01"] = ["☐", "bot01", "a@x", ":10", "● Running", "", "", "", "", "", "", "", "", "", "[View]"]
    rows["bot02"] = ["☐", "bot02", "b@x", ":11", "● Running", "", "", "", "", "", "", "", "", "", "[View]"]
    c._manager = type("M", (), {"bots": []})()
    c._update_selection_only()
    # bot02 selected -> ☑; bot01 not selected -> stays ☐
    assert rows["bot01"][0] == "☐"
    assert rows["bot02"][0] == "☑"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_on_tree_select_does_not_call_update_rows tests/test_bot_console.py::test_update_selection_only_rewrites_sel_column -v`
Expected: FAIL — `_update_selection_only` doesn't exist / `_on_tree_select` still calls `_update_rows`.

- [ ] **Step 3: Implement**

Add the lightweight method and change `_on_tree_select`:

```python
    def _on_tree_select(self, _event: Any = None) -> None:
        self._update_selection_only()

    def _update_selection_only(self) -> None:
        """Re-render only the ☑/☐ selection column after a selection change.

        The full _update_rows (stats, location detection, tooltips) is
        expensive and already runs on the 2s poll; a selection only changes
        the checkbox glyph, so update that alone for instant feedback.
        """
        selected = set(self._tree.selection())
        for bot in self._manager.bots:
            if not self._tree.exists(bot.name):
                continue
            try:
                values = list(self._tree.item(bot.name, "values") or ())
            except Exception:  # noqa: BLE001 - a missing row must not abort
                continue
            if not values:
                continue
            values[0] = "☑" if bot.name in selected else "☐"
            self._tree.item(bot.name, values=tuple(values))
```

Note: `self._tree.item(iid, "values")` returns the current values tuple; the first element (index 0) is the `sel` glyph (column key `"sel"`, defined at `_setup_bot_list`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_console.py::test_on_tree_select_does_not_call_update_rows tests/test_bot_console.py::test_update_selection_only_rewrites_sel_column -v`
Expected: PASS.

- [ ] **Step 5: Run the full console suite + lint**

Run: `source .venv/bin/activate && pytest tests/test_bot_console.py -q`
Expected: PASS.

Run: `ruff check viewer/bot_console.py tests/test_bot_console.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "perf: selection updates only the checkbox column (instant feedback)"
```

---
### Task 2: Live verification

**Files:**
- none (verification only)

**Interfaces:**
- Consumes: the feature from Task 1.

- [ ] **Step 1: Run full unit test suite**

Run: `source .venv/bin/activate && pytest tests/ -q`
Expected: PASS except the 2 pre-existing unrelated failures (test_shm_screen, test_input_interactive).

- [ ] **Step 2: Confirm selection is instant**

Restart the console with a display, select bots repeatedly. Each selection's checkbox should update immediately (<100ms), independent of the 2s poll.

- [ ] **Step 3: Confirm the full update still runs on the poll**

The status/location/CPU columns still refresh every 2s (the `_poll` still calls `_update_rows`).

- [ ] **Step 4: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from selection perf verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
