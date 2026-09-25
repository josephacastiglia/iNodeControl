/* iMouse2 frame bridge, GPL-3.0-or-later, same terms as UxPlay.
 * Opt-in through IMOUSE2_FRAME_PIPE. No vendor component is used.
 * Wire format: uint32 little-endian length then bottom-up 24-bit BMP.
 * A zero length announces a stopped session. Named pipe stays local.
 */
#ifdef _WIN32
#include <windows.h>
#include <gst/app/gstappsink.h>
#include <gst/video/video.h>
static HANDLE imouse_pipe = INVALID_HANDLE_VALUE;
static GMutex imouse_gate;
static guint8 *imouse_bmp = NULL;
static gsize imouse_capacity = 0;

static gboolean imouse_write(const void *buffer, DWORD size) {
    const char *path = g_getenv("IMOUSE2_FRAME_PIPE");
    if (!path || !path[0]) return FALSE;
    if (imouse_pipe == INVALID_HANDLE_VALUE)
        imouse_pipe = CreateFileA(path, GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (imouse_pipe == INVALID_HANDLE_VALUE) return FALSE;
    const guint8 *bytes = buffer;
    while (size) {
        DWORD written = 0;
        if (!WriteFile(imouse_pipe, bytes, size, &written, NULL) || !written) {
            CloseHandle(imouse_pipe); imouse_pipe = INVALID_HANDLE_VALUE; return FALSE;
        }
        bytes += written; size -= written;
    }
    return TRUE;
}
static void imouse_stopped(void) {
    guint32 zero = 0;
    g_mutex_lock(&imouse_gate);
    imouse_write(&zero, 4);
    g_mutex_unlock(&imouse_gate);
}
static GstFlowReturn imouse_sample(GstAppSink *sink, gpointer unused) {
    GstSample *sample = gst_app_sink_pull_sample(sink);
    if (!sample) return GST_FLOW_OK;
    GstVideoInfo info;
    GstVideoFrame frame;
    if (!gst_video_info_from_caps(&info, gst_sample_get_caps(sample)) ||
        GST_VIDEO_INFO_FORMAT(&info) != GST_VIDEO_FORMAT_BGR ||
        !gst_video_frame_map(&frame, &info, gst_sample_get_buffer(sample), GST_MAP_READ)) {
        gst_sample_unref(sample); return GST_FLOW_OK;
    }
    guint32 width = GST_VIDEO_INFO_WIDTH(&info), height = GST_VIDEO_INFO_HEIGHT(&info);
    guint32 stride = (width * 3 + 3) & ~3, size = 54 + stride * height;
    if (!width || !height || width > 4096 || height > 4096) {
        gst_video_frame_unmap(&frame); gst_sample_unref(sample); return GST_FLOW_OK;
    }
    g_mutex_lock(&imouse_gate);
    if (imouse_capacity < size) { imouse_bmp = g_realloc(imouse_bmp, size); imouse_capacity = size; }
    memset(imouse_bmp, 0, 54);
    imouse_bmp[0] = 'B'; imouse_bmp[1] = 'M';
    GST_WRITE_UINT32_LE(imouse_bmp + 2, size);
    GST_WRITE_UINT32_LE(imouse_bmp + 10, 54);
    GST_WRITE_UINT32_LE(imouse_bmp + 14, 40);
    GST_WRITE_UINT32_LE(imouse_bmp + 18, width);
    GST_WRITE_UINT32_LE(imouse_bmp + 22, height);
    GST_WRITE_UINT16_LE(imouse_bmp + 26, 1);
    GST_WRITE_UINT16_LE(imouse_bmp + 28, 24);
    GST_WRITE_UINT32_LE(imouse_bmp + 34, stride * height);
    const guint8 *pixels = GST_VIDEO_FRAME_PLANE_DATA(&frame, 0);
    gint input_stride = GST_VIDEO_FRAME_PLANE_STRIDE(&frame, 0);
    for (guint32 y = 0; y < height; ++y) {
        guint8 *row = imouse_bmp + 54 + (height - 1 - y) * stride;
        memcpy(row, pixels + y * input_stride, width * 3);
        memset(row + width * 3, 0, stride - width * 3);
    }
    guint8 length[4]; GST_WRITE_UINT32_LE(length, size);
    if (imouse_write(length, 4)) imouse_write(imouse_bmp, size);
    g_mutex_unlock(&imouse_gate);
    gst_video_frame_unmap(&frame);
    gst_sample_unref(sample);
    return GST_FLOW_OK;
}
static void imouse_attach(GstElement *pipeline, const char *codec) {
    if (!g_getenv("IMOUSE2_FRAME_PIPE")) return;
    gchar *name = g_strdup_printf("appsink_%s", codec);
    GstElement *sink = gst_bin_get_by_name(GST_BIN(pipeline), name);
    g_free(name);
    if (sink) {
        GstCaps *caps = gst_caps_from_string("video/x-raw,format=BGR,width=500,height=1080,pixel-aspect-ratio=1/1");
        gst_app_sink_set_caps(GST_APP_SINK(sink), caps);
        gst_caps_unref(caps);
        g_object_set(sink, "emit-signals", TRUE, "max-buffers", 1, "drop", TRUE, "sync", FALSE, NULL);
        g_signal_connect(sink, "new-sample", G_CALLBACK(imouse_sample), NULL);
        gst_object_unref(sink);
    }
}
#else
#define imouse_attach(pipeline,codec) ((void)0)
#define imouse_stopped() ((void)0)
#endif
