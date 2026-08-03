/* sendtext.c - focus the game's login field and type via SendInput.
 *
 * Mimics AutoHotkey: MouseMove+Click to focus the field, then Send/SendText.
 * Uses KEYEVENTF_UNICODE so '@' and uppercase work without shift/X keymap.
 * Specials: {Enter} {Backspace} {Tab} {Esc} {CtrlA} {Delete}
 *
 * Usage:
 *   sendtext.exe <text> [x y]
 *   sendtext.exe "{CtrlA}sr02-05@mx1.us" 365 156
 *
 * Build:
 *   x86_64-w64-mingw32-gcc -o sendtext.exe sendtext.c -luser32
 */

#include <windows.h>
#include <stdio.h>
#include <string.h>

static void press_key(WORD vk) {
    INPUT in[2] = {0};
    in[0].type = INPUT_KEYBOARD; in[0].ki.wVk = vk;
    in[1].type = INPUT_KEYBOARD; in[1].ki.wVk = vk; in[1].ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(2, in, sizeof(INPUT));
}

static void press_ctrl_a(void) {
    INPUT in[4] = {0};
    in[0].type = INPUT_KEYBOARD; in[0].ki.wVk = VK_CONTROL;
    in[1].type = INPUT_KEYBOARD; in[1].ki.wVk = 'A';
    in[2].type = INPUT_KEYBOARD; in[2].ki.wVk = 'A'; in[2].ki.dwFlags = KEYEVENTF_KEYUP;
    in[3].type = INPUT_KEYBOARD; in[3].ki.wVk = VK_CONTROL; in[3].ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(4, in, sizeof(INPUT));
}

static void send_unicode(const char *s, int len) {
    wchar_t w = 0;
    int n = MultiByteToWideChar(CP_UTF8, 0, s, len, &w, 1);
    if (n <= 0) return;
    INPUT in[2] = {0};
    in[0].type = INPUT_KEYBOARD; in[0].ki.wVk = 0; in[0].ki.wScan = (WORD)w; in[0].ki.dwFlags = KEYEVENTF_UNICODE;
    in[1].type = INPUT_KEYBOARD; in[1].ki.wVk = 0; in[1].ki.wScan = (WORD)w; in[1].ki.dwFlags = KEYEVENTF_UNICODE|KEYEVENTF_KEYUP;
    SendInput(2, in, sizeof(INPUT));
}

static void click_at(int x, int y) {
    SetCursorPos(x, y);
    Sleep(60);
    mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0);
    Sleep(60);
    mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0);
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: sendtext.exe <text> [x y]\n"); return 1; }
    HWND h = FindWindowA(NULL, "Doomsday: Last Survivors");
    if (h) { ShowWindow(h, SW_RESTORE); SetForegroundWindow(h); }
    Sleep(150);
    const char *s = argv[1];
    if (argc >= 4) { click_at(atoi(argv[2]), atoi(argv[3])); Sleep(150); }
    size_t n = strlen(s);
    for (size_t i = 0; i < n;) {
        if (s[i] == '{') {
            const char *end = strchr(s + i, '}');
            if (end) {
                size_t tok = (size_t)(end - (s + i) - 1);
                if (tok == 5 && strncmp(s + i + 1, "Enter", 5) == 0) press_key(VK_RETURN);
                else if (tok == 9 && strncmp(s + i + 1, "Backspace", 9) == 0) press_key(VK_BACK);
                else if (tok == 3 && strncmp(s + i + 1, "Tab", 3) == 0) press_key(VK_TAB);
                else if (tok >= 3 && strncmp(s + i + 1, "Esc", 3) == 0) press_key(VK_ESCAPE);
                else if (tok == 5 && strncmp(s + i + 1, "CtrlA", 5) == 0) press_ctrl_a();
                else if (tok == 6 && strncmp(s + i + 1, "Delete", 6) == 0) press_key(VK_DELETE);
                else send_unicode(s + i, (int)(end - s - i + 1));
                i = (size_t)(end - s) + 1;
                continue;
            }
        }
        send_unicode(s + i, 1);
        i++;
    }
    return 0;
}
