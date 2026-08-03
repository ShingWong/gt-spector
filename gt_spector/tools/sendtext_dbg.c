#include <windows.h>
#include <stdio.h>
int main(int argc, char **argv) {
    HWND h = FindWindowA(NULL, "Doomsday: Last Survivors");
    if (!h) { printf("NO_WINDOW\n"); return 1; }
    printf("WINDOW=%p fg=%p\n", (void*)h, (void*)GetForegroundWindow());
    ShowWindow(h, SW_RESTORE);
    SetForegroundWindow(h);
    Sleep(200);
    printf("after-activate fg=%p isgame=%d\n", (void*)GetForegroundWindow(), GetForegroundWindow()==h);
    // type 'a'
    INPUT in[2]={0};
    in[0].type=INPUT_KEYBOARD; in[0].ki.wVk=0; in[0].ki.wScan='a'; in[0].ki.dwFlags=KEYEVENTF_UNICODE;
    in[1].type=INPUT_KEYBOARD; in[1].ki.wVk=0; in[1].ki.wScan='a'; in[1].ki.dwFlags=KEYEVENTF_UNICODE|KEYEVENTF_KEYUP;
    UINT sent = SendInput(2, in, sizeof(INPUT));
    printf("sendinput sent=%u\n", sent);
    return 0;
}
