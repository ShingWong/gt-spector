/* sendtextd.c - persistent SendInput typist daemon.
 *
 * Stays resident and watches a command file (default C:\sendtext_cmd.txt).
 * Each line is a command:
 *   <text>                type text via SendInput (KEYEVENTF_UNICODE)
 *   X,Y,<text>            move mouse to screen (X,Y), click, then type
 * Lines support specials: {Enter} {Backspace} {Tab} {Esc} {CtrlA} {Delete}
 *
 * After executing a line the daemon truncates the file, so the Linux side can
 * simply write a command and poll for its disappearance.
 *
 * This fixes uppercase/@ typing anywhere in the game (login form, chat, ...)
 * because KEYEVENTF_UNICODE bypasses the broken X11 shift-key translation.
 *
 * Build:
 *   x86_64-w64-mingw32-gcc -O2 -o sendtextd.exe sendtextd.c -luser32
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

static void activate_game(void) {
    HWND h = FindWindowA(NULL, "Doomsday: Last Survivors");
    if (h) { ShowWindow(h, SW_RESTORE); SetForegroundWindow(h); }
}

static void type_text(const char *s) {
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
}

static void process_command(const char *line) {
    /* optional "X,Y,<text>" -> click then type */
    const char *c1 = strchr(line, ',');
    const char *c2 = c1 ? strchr(c1 + 1, ',') : NULL;
    if (c1 && c2) {
        int x = atoi(line);
        int y = atoi(c1 + 1);
        activate_game();
        Sleep(60);
        click_at(x, y);
        Sleep(120);
        type_text(c2 + 1);
    } else {
        activate_game();
        Sleep(60);
        type_text(line);
    }
}

int main(int argc, char **argv) {
    const char *path = (argc >= 2) ? argv[1] : "C:\\sendtext_cmd.txt";
    FILE *f;
    char buf[8192];
    DWORD last = 0;

    activate_game();
    fprintf(stderr, "sendtextd: watching %s\n", path);
    fflush(stderr);

    for (;;) {
        Sleep(150);
        f = fopen(path, "r");
        if (!f) continue;
        if (fgets(buf, sizeof(buf), f)) {
            /* only process if the file changed since last read */
            HANDLE h = CreateFileA(path, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
            DWORD size = h != INVALID_HANDLE_VALUE ? GetFileSize(h, NULL) : 0;
            if (h != INVALID_HANDLE_VALUE) CloseHandle(h);
            if (size != last && buf[0] && buf[0] != '\n') {
                size_t len = strlen(buf);
                while (len > 0 && (buf[len-1] == '\n' || buf[len-1] == '\r')) buf[--len] = 0;
                process_command(buf);
                last = size;
            }
        }
        fclose(f);
        /* truncate so the sender sees completion */
        f = fopen(path, "w");
        if (f) fclose(f);
        if (last) last = 0;
    }
    return 0;
}
