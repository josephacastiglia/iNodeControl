
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stdint.h>
#include <windows.h>
#include <psapi.h>
#include <plist/plist.h>
static int parsed, released;
static void parse_report(const char *p, uint32_t n, plist_t *root) {
    plist_from_bin(p, n, root); if (*root) parsed++;
}
static void release_report(plist_t root) {
    if (root) released++; plist_free(root);
}
static unsigned long long memory(void) {
    PROCESS_MEMORY_COUNTERS_EX m = {0}; m.cb = sizeof(m);
    if (!GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&m, sizeof(m))) exit(5);
    return m.PrivateUsage;
}
#define plist_from_bin parse_report
#define plist_free release_report
#define logger_log(...) ((void)0)
static char *utils_data_to_string(const void *p, int n, int width) {
    (void)p; (void)n; (void)width; return calloc(1, 32);
}
static void process_report(unsigned char *payload, int payload_size, bool show, bool logger_debug) {
    struct {bool show_client_FPS_data;} state = {show}, *raop_rtp_mirror = &state;
    switch (5) {
case 0x05:
                logger_log(raop_rtp_mirror->logger, LOGGER_DEBUG, "\nReceived video streaming performance info packet from client:"
                           " payload_size %d header %s ts_raw = %llu", payload_size, packet_description, ntp_timestamp_raw);
                /* payloads with packet[4] = 0x05 have no timestamp, and carry video info from the client as a binary plist *
                 * Sometimes (e.g, when the client has a locked screen), there is a 25kB trailer attached to the packet.    *
                 * This 25000 Byte trailer with unidentified content seems to be the same data each time it is sent.        */

                if (payload_size) {
                    //char *str = utils_data_to_string(packet, 128, 16);
                    //logger_log(raop_rtp_mirror->logger, LOGGER_WARNING, "type 5 video packet header:\n%s", str);
                    //free (str);
		    
                    int plist_size = payload_size;
                    if (payload_size > 25000) {
                        plist_size = payload_size - 25000;
                        if (logger_debug) {
                            char *str = utils_data_to_string(payload + plist_size, 16, 16);
                            logger_log(raop_rtp_mirror->logger, LOGGER_DEBUG,
                                       "video_info packet had 25kB trailer; first 16 bytes are:\n%s", str);
                        free(str);
                        }
                    }
                    if (plist_size) {
                        char *plist_xml = NULL;
                        uint32_t plist_len = 0;
                        plist_t root_node = NULL;
                        plist_from_bin((char *) payload, plist_size, &root_node);
                        if (raop_rtp_mirror->show_client_FPS_data) {
                            plist_to_xml(root_node, &plist_xml, &plist_len);
                            logger_log(raop_rtp_mirror->logger, LOGGER_INFO, "%s", plist_xml);
                            free(plist_xml);
                        }
                    }
                }
                break;

    }
}
#undef plist_from_bin
#undef plist_free
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    bool show = atoi(argv[1]), trailer = atoi(argv[2]), malformed = atoi(argv[3]);
    plist_t root = plist_new_dict();
    for (int i = 0; i < 24; i++) {
        char key[32]; snprintf(key, sizeof(key), "synthetic-metric-%d", i);
        plist_dict_set_item(root, key, plist_new_uint(i));
    }
    char *bin = NULL; uint32_t size = 0; plist_to_bin(root, &bin, &size); plist_free(root);
    int bytes = size + (trailer ? 25000 : 0);
    unsigned char *payload = calloc(1, bytes); memcpy(payload, bin, size); plist_to_bin_free(bin);
    if (malformed) memset(payload, 0, size);
    unsigned long long before = memory();
    for (int i = 0; i < 10000; i++) process_report(payload, bytes, show, true);
    unsigned long long after = memory();
    free(payload);
    printf("{\"parsed\":%d,\"released\":%d,\"private_growth_bytes\":%lld}\n", parsed, released, (long long)after-(long long)before);
    return parsed == released && parsed == (malformed ? 0 : 10000) ? 0 : 1;
}
