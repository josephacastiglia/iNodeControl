/* Offline video/frame-bridge probe. No UxPlay server, network, or device code.
 * Includes the production bridge unchanged; GPL-3.0-or-later like that file. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <psapi.h>
#include <gst/gst.h>
#include "../airplay/uxplay/renderers/imouse_frame_pipe.h"

static volatile LONG frames, received, invalid;
static HANDLE server;
static gboolean bridge;

static gboolean read_exact(void *target, DWORD size) {
    char *p = target;
    while (size) {
        DWORD n = 0;
        if (!ReadFile(server, p, size, &n, NULL) || !n) return FALSE;
        p += n; size -= n;
    }
    return TRUE;
}

static DWORD WINAPI consume(LPVOID unused) {
    (void)unused;
    if (!ConnectNamedPipe(server, NULL) && GetLastError() != ERROR_PIPE_CONNECTED) {
        InterlockedIncrement(&invalid); return 1;
    }
    const DWORD expected = 54 + 1500 * 1080;
    guint8 *bmp = g_malloc(expected);
    guint8 prefix[4];
    while (read_exact(prefix, 4)) {
        guint32 n = GST_READ_UINT32_LE(prefix);
        if (!n) break;
        if (n != expected || !read_exact(bmp, n) || bmp[0] != 'B' || bmp[1] != 'M' ||
            GST_READ_UINT32_LE(bmp + 18) != 500 || GST_READ_UINT32_LE(bmp + 22) != 1080) {
            InterlockedIncrement(&invalid); break;
        }
        InterlockedIncrement(&received);
    }
    g_free(bmp);
    return 0;
}

static GstFlowReturn sample(GstAppSink *sink, gpointer unused) {
    (void)unused;
    GstFlowReturn result = GST_FLOW_OK;
    if (bridge) result = imouse_sample(sink, NULL);
    else {
        GstSample *s = gst_app_sink_pull_sample(sink);
        if (!s) return GST_FLOW_EOS;
        gst_sample_unref(s);
    }
    InterlockedIncrement(&frames);
    return result;
}

static void memory(double seconds) {
    PROCESS_MEMORY_COUNTERS_EX m = {0}; m.cb = sizeof(m);
    if (!GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&m, sizeof(m))) exit(5);
    printf("{\"seconds\":%.3f,\"private_bytes\":%llu,\"working_set_bytes\":%llu,\"frames\":%ld,\"received\":%ld}\n",
        seconds, (unsigned long long)m.PrivateUsage, (unsigned long long)m.WorkingSetSize,
        InterlockedCompareExchange(&frames, 0, 0), InterlockedCompareExchange(&received, 0, 0));
    fflush(stdout);
}

int main(int argc, char **argv) {
    if (argc != 4 || (strcmp(argv[1], "bridge") && strcmp(argv[1], "discard")) ||
        (strcmp(argv[2], "raw") && strcmp(argv[2], "h264"))) return 2;
    char *end = NULL; long seconds = strtol(argv[3], &end, 10);
    if (*end || seconds < 2 || seconds > 1800) return 2;
    bridge = !strcmp(argv[1], "bridge");
    /* Never inherit an installed receiver's pipe; only this PID's private pipe. */
    g_unsetenv("IMOUSE2_FRAME_PIPE");
    HANDLE consumer = NULL;
    if (bridge) {
        char name[128]; snprintf(name, sizeof(name), "\\\\.\\pipe\\imouse-offline-memory-%lu", GetCurrentProcessId());
        server = CreateNamedPipeA(name, PIPE_ACCESS_INBOUND | FILE_FLAG_FIRST_PIPE_INSTANCE,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
            1, 65536, 65536, 0, NULL);
        if (server == INVALID_HANDLE_VALUE) return 3;
        g_setenv("IMOUSE2_FRAME_PIPE", name, TRUE);
        consumer = CreateThread(NULL, 0, consume, NULL, 0, NULL);
        if (!consumer) return 3;
    }
    gst_init(NULL, NULL);
    const char *decode = !strcmp(argv[2], "h264") ?
        "openh264enc complexity=low ! h264parse ! avdec_h264 ! " : "";
    gchar *description = g_strdup_printf(
        "videotestsrc is-live=true pattern=ball ! video/x-raw,format=I420,width=500,height=1080,framerate=30/1 ! "
        "%svideoconvert ! videoscale ! video/x-raw,format=BGR,width=500,height=1080 ! "
        "appsink name=probe emit-signals=true max-buffers=1 drop=true sync=false", decode);
    fprintf(stderr, "pipeline: %s\nGStreamer: %s\n", description, gst_version_string());
    GError *error = NULL;
    GstElement *pipeline = gst_parse_launch(description, &error); g_free(description);
    if (error || !pipeline) { fprintf(stderr, "pipeline error: %s\n", error ? error->message : "null"); return 4; }
    GstElement *sink = gst_bin_get_by_name(GST_BIN(pipeline), "probe");
    g_signal_connect(sink, "new-sample", G_CALLBACK(sample), NULL);
    gst_object_unref(sink);
    GstBus *bus = gst_element_get_bus(pipeline);
    if (gst_element_set_state(pipeline, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE) return 4;
    ULONGLONG start = GetTickCount64(), next = start;
    int result = 0;
    while (GetTickCount64() - start < (ULONGLONG)seconds * 1000) {
        GstMessage *msg = gst_bus_timed_pop(bus, 100 * GST_MSECOND);
        if (msg) {
            if (GST_MESSAGE_TYPE(msg) == GST_MESSAGE_ERROR) {
                gchar *debug = NULL; gst_message_parse_error(msg, &error, &debug);
                fprintf(stderr, "%s\n", error->message); g_clear_error(&error); g_free(debug); result = 4;
            }
            gst_message_unref(msg);
        }
        ULONGLONG now = GetTickCount64();
        if (now >= next) { memory((now - start) / 1000.0); next = now + 1000; }
        if (result) break;
    }
    gst_element_set_state(pipeline, GST_STATE_NULL);
    gst_object_unref(bus); gst_object_unref(pipeline);
    if (bridge) {
        imouse_stopped();
        if (imouse_pipe != INVALID_HANDLE_VALUE) { CloseHandle(imouse_pipe); imouse_pipe = INVALID_HANDLE_VALUE; }
        if (WaitForSingleObject(consumer, 5000) != WAIT_OBJECT_0) return 6;
        CloseHandle(consumer); CloseHandle(server);
    }
    memory((GetTickCount64() - start) / 1000.0);
    HMODULE modules[1024]; DWORD needed = 0;
    if (EnumProcessModules(GetCurrentProcess(), modules, sizeof(modules), &needed) && needed <= sizeof(modules)) {
        for (DWORD i = 0; i < needed / sizeof(HMODULE); i++) {
            char path[32768];
            if (GetModuleFileNameExA(GetCurrentProcess(), modules[i], path, sizeof(path))) fprintf(stderr, "module: %s\n", path);
        }
    }
    fprintf(stderr, "frames=%ld received=%ld invalid=%ld\n", frames, received, invalid);
    if (!frames || invalid || (bridge && frames != received)) result = 7;
    g_free(imouse_bmp); gst_deinit();
    return result;
}
