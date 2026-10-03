#ifndef FUJIREALM_AMIGA_NET_H
#define FUJIREALM_AMIGA_NET_H

/* A TCP byte stream through FujiNet NIO (fujinet-nio.device), standing in
 * for the Atari/Lynx FujiNet Netstream.  NIO TCP sessions need sequential
 * read/write stream offsets, which this layer tracks. */

#define NET_RX_CAP 2048

struct net_stream {
    unsigned short handle;       /* fn_handle_t: 16-bit, never narrow it */
    unsigned char open;
    unsigned long rx_offset;
    unsigned long tx_offset;
    /* Received bytes waiting for the protocol parsers. */
    unsigned char rx[NET_RX_CAP];
    unsigned rx_read;
    unsigned rx_write;
    unsigned rx_count;
    /* Link statistics, for the diagnostics line. */
    unsigned long rx_total;
    unsigned long tx_total;
    unsigned long polls;
    unsigned char last_error;
};

/* Bring up FujiNet NIO. 0 on success. */
int net_init(void);
void net_done(void);

/* Open tcp://host:port and wait (bounded) until it accepts writes.
 * Returns 0 on success. */
int net_open(struct net_stream *s, const char *host, unsigned port);
void net_close(struct net_stream *s);

/* Send all of buf; retries while NIO reports not-ready. 0 on success. */
int net_write(struct net_stream *s, const unsigned char *buf, unsigned len);

/* One FujiBus read exchange (up to 512 bytes) into the ring. Returns the
 * number of bytes received, 0 if none were waiting, -1 on a link error.
 * Each call costs a full serial round trip (~20 ms), so callers poll at a
 * bounded rate rather than every loop. */
int net_poll(struct net_stream *s);

/* Take one byte from the ring; 0 if empty. */
int net_get(struct net_stream *s, unsigned char *byte);

const char *net_error_text(const struct net_stream *s);

#endif
