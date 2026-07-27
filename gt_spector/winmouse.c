// Send mouse events via Win32 SendInput API
// Compile: x86_64-w64-mingw32-gcc -O2 -s -o winmouse.exe winmouse.c -luser32
// Actions: 1=left_click 2=left_down 3=left_up 4=right_click
//          5=scroll_down 6=scroll_up 7=move 8=drag_move

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char* argv[]) {
    if (argc < 3) {
        fprintf(stderr, "Usage: winmouse.exe <x> <y> <action>\n");
        return 1;
    }

    int x = atoi(argv[1]);
    int y = atoi(argv[2]);
    int action = argc > 3 ? atoi(argv[3]) : 1;

    INPUT in[2] = {0};
    int count = 0;

    switch (action) {
        case 1: // left click
            in[0].type = INPUT_MOUSE;
            in[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
            in[1].type = INPUT_MOUSE;
            in[1].mi.dwFlags = MOUSEEVENTF_LEFTUP;
            count = 2;
            break;
        case 2: // left down
            in[0].type = INPUT_MOUSE;
            in[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
            count = 1;
            break;
        case 3: // left up
            in[0].type = INPUT_MOUSE;
            in[0].mi.dwFlags = MOUSEEVENTF_LEFTUP;
            count = 1;
            break;
        case 4: // right click
            in[0].type = INPUT_MOUSE;
            in[0].mi.dwFlags = MOUSEEVENTF_RIGHTDOWN;
            in[1].type = INPUT_MOUSE;
            in[1].mi.dwFlags = MOUSEEVENTF_RIGHTUP;
            count = 2;
            break;
        case 5: // scroll down
            in[0].type = INPUT_MOUSE;
            in[0].mi.dwFlags = MOUSEEVENTF_WHEEL;
            in[0].mi.mouseData = -120;
            count = 1;
            break;
        case 6: // scroll up
            in[0].type = INPUT_MOUSE;
            in[0].mi.dwFlags = MOUSEEVENTF_WHEEL;
            in[0].mi.mouseData = 120;
            count = 1;
            break;
        case 7: // move to (x,y)
            in[0].type = INPUT_MOUSE;
            in[0].mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE;
            in[0].mi.dx = (x * 65535) / 1152;
            in[0].mi.dy = (y * 65535) / 864;
            count = 1;
            break;
        case 8: // drag move (left button held) to (x,y)
            in[0].type = INPUT_MOUSE;
            in[0].mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN;
            in[0].mi.dx = (x * 65535) / 1152;
            in[0].mi.dy = (y * 65535) / 864;
            count = 1;
            break;
        default:
            return 1;
    }

    if (count > 0)
        SendInput(count, in, sizeof(INPUT));
    return 0;
}
