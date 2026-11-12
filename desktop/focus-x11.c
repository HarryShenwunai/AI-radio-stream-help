/* Restore the previously active application after an explicit collapse.
 * Only X11 window identifiers are observed. No titles, pixels or input are read.
 * The one stdin command is "restore"; renderer-supplied identifiers are absent.
 */
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <unistd.h>

static int ignore_x_error(Display *display, XErrorEvent *event) {
    (void)display; (void)event; return 0;
}
static Window active_window(Display *d, Window root, Atom active) {
    Atom type; int format; unsigned long count, remaining; unsigned char *data = NULL;
    Window result = None;
    if (XGetWindowProperty(d, root, active, 0, 1, False, XA_WINDOW,
        &type, &format, &count, &remaining, &data) == Success && data && format == 32 && count == 1)
        result = *(Window *)data;
    if (data) XFree(data);
    return result;
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    char *end; unsigned long own = strtoul(argv[1], &end, 10);
    if (!own || *end) return 2;
    Display *d = XOpenDisplay(NULL); if (!d) return 3;
    XSetErrorHandler(ignore_x_error);
    Window root = DefaultRootWindow(d);
    Atom active = XInternAtom(d, "_NET_ACTIVE_WINDOW", False);
    XSelectInput(d, root, PropertyChangeMask);
    Window previous = active_window(d, root, active);
    if (previous == own) previous = None;
    XFlush(d); puts("ready"); fflush(stdout);
    char line[32]; size_t used = 0;
    for (;;) {
        while (XPending(d)) {
            XEvent event; XNextEvent(d, &event);
            if (event.type == PropertyNotify && event.xproperty.atom == active) {
                Window current = active_window(d, root, active);
                if (current && current != own) previous = current;
            }
        }
        fd_set readfds; FD_ZERO(&readfds); FD_SET(STDIN_FILENO, &readfds);
        int xfd = ConnectionNumber(d); FD_SET(xfd, &readfds);
        if (select(xfd + 1, &readfds, NULL, NULL, NULL) < 0) { if (errno == EINTR) continue; break; }
        if (FD_ISSET(STDIN_FILENO, &readfds)) {
            char input[32]; ssize_t n = read(STDIN_FILENO, input, sizeof(input));
            if (n <= 0) break;
            for (ssize_t i = 0; i < n; i++) {
                if (input[i] == '\n') {
                    line[used] = 0;
                    if (!strcmp(line, "restore") && previous) {
                        XEvent request = {0}; request.xclient.type = ClientMessage;
                        request.xclient.display = d; request.xclient.window = previous;
                        request.xclient.message_type = active; request.xclient.format = 32;
                        request.xclient.data.l[0] = 2; request.xclient.data.l[1] = CurrentTime;
                        XSendEvent(d, root, False, SubstructureRedirectMask | SubstructureNotifyMask, &request);
                        XFlush(d);
                    }
                    used = 0;
                } else if (used < sizeof(line) - 1) line[used++] = input[i];
            }
        }
    }
    XCloseDisplay(d); return 0;
}
