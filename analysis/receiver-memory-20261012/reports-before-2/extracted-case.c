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
