// Send mouse events via Win32 SendInput API
// Compile: x86_64-w64-mingw32-gcc -O2 -s -o winmouse.exe winmouse.c -luser32
// Actions: 1=left_click 2=left_down 3=left_up 4=right_click
//          5=scroll_down 6=scroll_up 7=move_abs 8=drag_move_abs

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

static void send_move(int x, int y, int hold_left) {
    INPUT in = {0};
    in.type = INPUT_MOUSE;
    in.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE;
    if (hold_left) in.mi.dwFlags |= MOUSEEVENTF_LEFTDOWN;
    in.mi.dx = (x * 65535) / 1152;
    in.mi.dy = (y * 65535) / 864;
    SendInput(1, &in, sizeof(INPUT));
}

int main(int argc, char* argv[]) {
    if (argc < 3) return 1;

    int x = atoi(argv[1]);
    int y = atoi(argv[2]);
    int action = argc > 3 ? atoi(argv[3]) : 1;

    if (action == 1) { // left click
        send_move(x, y, 0);
        Sleep(50);
        INPUT in[2] = {{0}};
        in[0].type = INPUT_MOUSE; in[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
        in[1].type = INPUT_MOUSE; in[1].mi.dwFlags = MOUSEEVENTF_LEFTUP;
        SendInput(2, in, sizeof(INPUT));
    } else if (action == 2) { // left down
        send_move(x, y, 0);
        Sleep(50);
        INPUT in = {0}; in.type = INPUT_MOUSE; in.mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
        SendInput(1, &in, sizeof(INPUT));
    } else if (action == 3) { // left up
        INPUT in = {0}; in.type = INPUT_MOUSE; in.mi.dwFlags = MOUSEEVENTF_LEFTUP;
        SendInput(1, &in, sizeof(INPUT));
    } else if (action == 4) { // right click (move + click)
        send_move(x, y, 0);
        Sleep(50);
        INPUT in[2] = {{0}};
        in[0].type = INPUT_MOUSE; in[0].mi.dwFlags = MOUSEEVENTF_RIGHTDOWN;
        in[1].type = INPUT_MOUSE; in[1].mi.dwFlags = MOUSEEVENTF_RIGHTUP;
        SendInput(2, in, sizeof(INPUT));
    } else if (action == 5) { // scroll down
        INPUT in = {0}; in.type = INPUT_MOUSE;
        in.mi.dwFlags = MOUSEEVENTF_WHEEL; in.mi.mouseData = -120;
        SendInput(1, &in, sizeof(INPUT));
    } else if (action == 6) { // scroll up
        INPUT in = {0}; in.type = INPUT_MOUSE;
        in.mi.dwFlags = MOUSEEVENTF_WHEEL; in.mi.mouseData = 120;
        SendInput(1, &in, sizeof(INPUT));
    } else if (action == 7) { // move absolute
        send_move(x, y, 0);
    } else if (action == 8) { // drag move (move + left held)
        send_move(x, y, 1);
    }

    Sleep(200);
    return 0;
}
