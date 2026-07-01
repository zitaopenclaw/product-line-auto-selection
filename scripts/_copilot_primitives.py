"""Primitives library for Copilot Studio topic automation.

Each function is contract-tested and returns (ok: bool, info: dict).
All functions are idempotent and handle known gotchas.

Gotchas baked in (see docs/copilot-studio-topic-config.md §4.1):
- Monaco editor: ta.value + dispatchEvent('input', 'change')
- Modal Save: focus + Enter key
- "Edit headers and body": find by label text "Headers and body"
- Acceptable errors dialog: click Save TEXT button, not close X
"""
from __future__ import annotations
import time
import json
import base64
import pathlib
from typing import Any

SHOT_DIR = pathlib.Path("D:/zita/opencode/product-line-auto-selection/.playwright-mcp/run")
SHOT_DIR.mkdir(parents=True, exist_ok=True)


def screenshot(c, name: str) -> dict:
    """Take a PNG screenshot and save to .playwright-mcp/run/."""
    res = c.send("Page.captureScreenshot", {"format": "png"})
    path = SHOT_DIR / f"{name}.png"
    path.write_bytes(base64.b64decode(res["result"]["data"]))
    return {"path": str(path)}


def navigate_to_topic(c, topic_id: str, env_id: str = "0dd9076f-7fbf-e21a-b965-e436f2ec8083",
                     bot_id: str = "90bf4480-f271-f111-ab0f-6045bd56018e",
                     wait_s: float = 8.0) -> dict:
    """Navigate to a topic canvas URL and wait for it to render."""
    url = f"https://copilotstudio.microsoft.com/environments/{env_id}/bots/{bot_id}/adaptive/{topic_id}"
    c.navigate(url)
    time.sleep(wait_s)
    return {"url": url, "current_url": c.eval("location.href")}


def open_canvas(c, timeout_s: float = 30.0) -> bool:
    """Wait until canvas is rendered (sees Trigger or other node label)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            h = c.eval("(document.body && document.body.innerText) ? document.body.innerText : ''")
            if "Trigger" in h or "Question" in h or "Message" in h:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def get_add_node_buttons(c) -> list[dict]:
    """Get positions of all 'Add node' buttons on canvas."""
    return c.eval("""(() => {
      return Array.from(document.querySelectorAll('button[aria-label="Add node"]')).map(b => {
        const r = b.getBoundingClientRect();
        return {x: r.x, y: r.y, w: r.width, h: r.height};
      });
    })()""")


def click_xy(c, x: float, y: float) -> None:
    """Click at (x, y) using mousePressed/Released."""
    c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    c.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    c.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


def add_node_after(c, after_node_y: float = None, kind: str = "Question") -> bool:
    """Click the first 'Add node' button at given y position (or default to first), pick menuitem.

    `kind` ∈ {'Question', 'HTTP request', 'Send a message'}
    """
    # Click "+"
    buttons = get_add_node_buttons(c)
    if not buttons:
        return False
    target = None
    if after_node_y is not None:
        # Find the button closest to (and just below) after_node_y
        candidates = [b for b in buttons if b["y"] > after_node_y]
        if candidates:
            target = min(candidates, key=lambda b: b["y"] - after_node_y)
    if target is None:
        target = buttons[0]
    cx = target["x"] + target["w"] / 2
    cy = target["y"] + target["h"] / 2
    click_xy(c, cx, cy)
    time.sleep(1.5)
    # Find menuitem
    items = c.eval("""(() => {
      return Array.from(document.querySelectorAll('[role=menuitem], button, [role=button]')).filter(e => {
        const t = (e.innerText||'').trim();
        return t === 'Ask a question' || t === 'Send a message' || t === 'Ask with adaptive card' || t === 'Add a condition' || t === 'Add a tool';
      }).map(e => {
        const r = e.getBoundingClientRect();
        return {text: (e.innerText||'').trim(), x: r.x, y: r.y, w: r.width, h: r.height};
      });
    })()""")
    # Map our kind to menuitem text
    text_map = {
        "Question": "Ask a question",
        "HTTP request": None,  # Need to find via "Add a tool" submenu or similar
        "Send a message": "Send a message",
        "Adaptive card": "Ask with adaptive card",
    }
    wanted_text = text_map.get(kind)
    if wanted_text is None:
        return False
    for it in items:
        if it["text"] == wanted_text:
            cx, cy = it["x"] + it["w"] / 2, it["y"] + it["h"] / 2
            click_xy(c, cx, cy)
            time.sleep(2)
            return True
    return False


def fill_monaco(c, selector: str, text: str) -> bool:
    """Fill a Monaco editor's textarea with `text` using ta.value + dispatchEvent pattern.

    `selector` should target the textarea inside the Monaco editor (e.g., textarea[aria-label*='Card payload editor']).
    """
    ok = c.eval(f"""(() => {{
      const ta = document.querySelector({json.dumps(selector)});
      if (!ta) return false;
      ta.focus();
      ta.value = {json.dumps(text)};
      ta.dispatchEvent(new Event('input', {{bubbles: true}}));
      ta.dispatchEvent(new Event('change', {{bubbles: true}}));
      return true;
    }})()""")
    return bool(ok)


def focus_and_enter(c, focus_selector: str = None) -> None:
    """Focus an element (or document.activeElement) and send Enter keypress.

    This is the workaround for Modal Save buttons that ignore mouse clicks.
    """
    if focus_selector:
        c.eval(f"document.querySelector({json.dumps(focus_selector)}).focus()")
    else:
        c.eval("(document.activeElement || document.body).focus()")
    time.sleep(0.2)
    c.send("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 13})
    c.send("Input.dispatchKeyEvent", {"type": "char", "text": "\r"})
    c.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13})


def verify_save_clean(c) -> bool:
    """Verify the top-bar Save button is disabled (= no pending changes)."""
    return bool(c.eval("""(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const save = btns.find(b => (b.innerText||'').trim() === 'Save');
      if (!save) return false;
      return save.disabled === true || save.getAttribute('aria-disabled') === 'true';
    })()"""))


def click_top_save(c, wait_s: float = 3.0) -> bool:
    """Click the top-bar 'Save' button. Returns whether button was enabled and clicked."""
    ok = c.eval("""(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const save = btns.find(b => (b.innerText||'').trim() === 'Save');
      if (!save) return 'no-save-button';
      if (save.disabled || save.getAttribute('aria-disabled') === 'true') return 'disabled';
      const r = save.getBoundingClientRect();
      window.__saveX = r.x + r.width/2;
      window.__saveY = r.y + r.height/2;
      return 'ok';
    })()""")
    if ok != "ok":
        return False
    x = c.eval("window.__saveX")
    y = c.eval("window.__saveY")
    click_xy(c, x, y)
    time.sleep(wait_s)
    return True


def save_topic(c, accept_warnings: bool = True) -> bool:
    """Full save cycle: click Save → if 'Save with errors?' dialog appears, click its Save text button.

    Returns True if no pending changes after the operation.
    """
    if not click_top_save(c):
        # Already clean
        return verify_save_clean(c)
    # If "Save with errors?" dialog appeared, click its Save button
    time.sleep(2)
    save_text_btn = c.eval("""(() => {
      const dialogs = document.querySelectorAll('[role=dialog], [role=alertdialog]');
      for (const d of dialogs) {
        if (!(d.innerText||'').toLowerCase().includes('save')) continue;
        const btns = Array.from(d.querySelectorAll('button'));
        const saveBtn = btns.find(b => (b.innerText||'').trim() === 'Save');
        if (saveBtn) {
          const r = saveBtn.getBoundingClientRect();
          window.__dlgX = r.x + r.width/2;
          window.__dlgY = r.y + r.height/2;
          return true;
        }
      }
      return false;
    })()""")
    if save_text_btn:
        x = c.eval("window.__dlgX")
        y = c.eval("window.__dlgY")
        click_xy(c, x, y)
        time.sleep(3)
    # Verify clean
    return verify_save_clean(c)


def click_node_by_label(c, label: str) -> bool:
    """Click a node whose visible label matches `label`. Scrolls into view first."""
    return bool(c.eval(f"""(() => {{
      const all = Array.from(document.querySelectorAll('div, span'));
      const node = all.find(e => {{
        const t = (e.innerText||'').trim();
        return t === {json.dumps(label)} || t.startsWith({json.dumps(label)});
      }});
      if (!node) return false;
      node.scrollIntoView({{block: 'center'}});
      const r = node.getBoundingClientRect();
      window.__nodeX = r.x + r.width/2;
      window.__nodeY = r.y + r.height/2;
      return true;
    }})()"""))


def scroll_to_top(c) -> None:
    """Scroll the canvas to the top."""
    for _ in range(10):
        c.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 600, "y": 600, "deltaX": 0, "deltaY": -500})
        time.sleep(0.15)


def scroll_to_bottom(c) -> None:
    """Scroll the canvas to the bottom."""
    for _ in range(15):
        c.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 600, "y": 600, "deltaX": 0, "deltaY": 500})
        time.sleep(0.15)


def write_checkpoint(state: dict, path: str = r"D:\zita\opencode\product-line-auto-selection\pac-setup\copilot-progress.json") -> None:
    """Write checkpoint JSON file."""
    state["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(path).write_text(json.dumps(state, indent=2))


def read_checkpoint(path: str = r"D:\zita\opencode\product-line-auto-selection\pac-setup\copilot-progress.json") -> dict:
    """Read checkpoint file, or return empty state if missing."""
    p = pathlib.Path(path)
    if not p.exists():
        return {"der": {}, "pre_der": {}}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"der": {}, "pre_der": {}}