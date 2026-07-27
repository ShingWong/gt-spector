"""Interactive input test for gt-spector.
Runs on :9 display and tests all input operations.
Prints PASS/FAIL for each test."""

import subprocess
import time
import sys

DISPLAY = ":9"
ENV = {"DISPLAY": DISPLAY}
PASS = 0
FAIL = 0

def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  PASS: {name}")
        PASS += 1
    except Exception as e:
        print(f"  FAIL: {name} — {e}")
        FAIL += 1

def xdotool(*args, timeout=5):
    return subprocess.run(["xdotool", *args], capture_output=True, text=True,
                          env=ENV, timeout=timeout, check=False)

def move_to(x, y):
    r = xdotool("mousemove", "--sync", str(x), str(y))
    if r.returncode != 0:
        raise RuntimeError(f"mousemove failed: {r.stderr}")

def get_pos():
    r = xdotool("getmouselocation")
    parts = r.stdout.strip().split()
    x = int(parts[0].split(":")[1])
    y = int(parts[1].split(":")[1])
    return x, y

def main():
    print("gt-spector Interactive Input Test")
    print(f"Display: {DISPLAY}")
    print()

    # 1. Mouse movement
    def test_move():
        move_to(500, 300)
        x, y = get_pos()
        assert x == 500 and y == 300, f"Expected (500,300) got ({x},{y})"
    test("Mouse move to absolute position", test_move)

    # 2. Relative move
    def test_move_relative():
        move_to(100, 100)
        xdotool("mousemove_relative", "--", "50", "25")
        x, y = get_pos()
        assert x == 150 and y == 125, f"Expected (150,125) got ({x},{y})"
    test("Mouse relative move", test_move_relative)

    # 3. Single click
    def test_click():
        move_to(200, 200)
        r = xdotool("click", "1")
        assert r.returncode == 0, f"click failed: {r.stderr}"
    test("Left click (button 1)", test_click)

    # 4. Double-click via --repeat
    def test_double_click_repeat():
        move_to(250, 250)
        r = xdotool("click", "--repeat", "2", "--delay", "50", "1")
        assert r.returncode == 0, f"double-click failed: {r.stderr}"
    test("Double-click (--repeat 2)", test_double_click_repeat)

    # 5. Double-click via two calls
    def test_double_click_two():
        move_to(300, 300)
        r1 = xdotool("click", "1")
        time.sleep(0.05)
        r2 = xdotool("click", "1")
        assert r1.returncode == 0 and r2.returncode == 0
    test("Double-click (two rapid clicks)", test_double_click_two)

    # 6. Right click
    def test_right_click():
        move_to(350, 350)
        r = xdotool("click", "3")
        assert r.returncode == 0
    test("Right click (button 3)", test_right_click)

    # 7. Middle click
    def test_middle_click():
        move_to(400, 400)
        r = xdotool("click", "2")
        assert r.returncode == 0
    test("Middle click (button 2)", test_middle_click)

    # 8. Scroll wheel up
    def test_scroll_up():
        r = xdotool("click", "4")
        assert r.returncode == 0
    test("Scroll wheel up (button 4)", test_scroll_up)

    # 9. Scroll wheel down
    def test_scroll_down():
        r = xdotool("click", "5")
        assert r.returncode == 0
    test("Scroll wheel down (button 5)", test_scroll_down)

    # 10. Drag (mousedown + mousemove + mouseup)
    def test_drag():
        move_to(100, 400)
        xdotool("mousedown", "1")
        xdotool("mousemove", "--sync", "300", "450")
        time.sleep(0.1)
        xdotool("mouseup", "1")
        x, y = get_pos()
        assert x == 300 and y == 450, f"Drag end expected (300,450) got ({x},{y})"
    test("Left drag (mousedown+move+mouseup)", test_drag)

    # 11. Right drag
    def test_right_drag():
        move_to(400, 400)
        xdotool("mousedown", "3")
        xdotool("mousemove", "--sync", "500", "450")
        time.sleep(0.1)
        xdotool("mouseup", "3")
        x, y = get_pos()
        assert x == 500 and y == 450
    test("Right drag (button 3)", test_right_drag)

    # 12. Keystrokes
    def test_key():
        r = xdotool("key", "Return")
        assert r.returncode == 0
    test("Key press (Return)", test_key)

    def test_type():
        r = xdotool("type", "hello world")
        assert r.returncode == 0
    test("Type text", test_type)

    # Summary
    print()
    print(f"Results: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
    if FAIL > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
