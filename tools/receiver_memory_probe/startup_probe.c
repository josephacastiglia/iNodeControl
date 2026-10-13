/* Offline renderer initialization, linked to the production renderer sources.
 * GPL-3.0-or-later, matching those sources. No UxPlay server, Bonjour or HID.
 * No encoded phone data, physical input, audio output or visible window.
 */
#include <stdio.h>
#include <windows.h>
#include <psapi.h>
#include <gst/gst.h>
#include "audio_renderer.h"
#include "video_renderer.h"

static int renderer_errors = 0;
static void log_message(void *context, int level, const char *message) {
    (void)context;
    fprintf(stderr, "renderer[%d]: %s\n", level, message);
    if (level <= LOGGER_ERR) renderer_errors++;
}

static void modules(void) {
    HMODULE list[1024]; DWORD bytes = 0;
    if (!EnumProcessModules(GetCurrentProcess(), list, sizeof(list), &bytes) || bytes > sizeof(list)) exit(5);
    for (DWORD i = 0; i < bytes / sizeof(HMODULE); i++) {
        wchar_t name[32768]; char utf8[131072];
        DWORD n = GetModuleFileNameW(list[i], name, 32768);
        if (!n || n >= 32768 || !WideCharToMultiByte(CP_UTF8, 0, name, -1, utf8, sizeof(utf8), NULL, NULL)) exit(5);
        fprintf(stderr, "module: %s\n", utf8);
    }
}

int main(void) {
    /* imouse_attach may otherwise inherit a real receiver's pipe. */
    g_unsetenv("IMOUSE2_FRAME_PIPE");
    if (!gstreamer_init()) return 2;
    logger_t *log = logger_init();
    logger_set_callback(log, log_message, NULL);
    logger_set_level(log, LOGGER_DEBUG);
    bool audio_sync = false, video_sync = false;
    videoflip_t flip[2] = { NONE, NONE };
    audio_renderer_init(log, "fakesink", &audio_sync, &video_sync, "");
    video_renderer_init(log, "offline-renderer-check", flip, "h264parse", "",
                        "avdec_h264", "videoconvert", "appsink", "",
                        false, false, false, false, 3, NULL);
    video_renderer_start();
    modules();
    video_renderer_stop();
    video_renderer_destroy();
    audio_renderer_destroy();
    logger_destroy(log);
    gst_deinit();
    if (renderer_errors) return 6;
    puts("Renderer initialization and teardown passed; no receiver or phone started.");
    return 0;
}
