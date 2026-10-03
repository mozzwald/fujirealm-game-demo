#include <string.h>

#include <proto/dos.h>

#include "fujinet-nio.h"
#include "net.h"

/* Delay() is in 1/50 s ticks. */
#define WRITE_WAIT_TICKS 500    /* 10 s of NOT_READY (covers the connect) */
#define READ_CHUNK 512

static unsigned char chunk[READ_CHUNK];

int net_init(void)
{
    return fn_init() == FN_OK && fn_is_ready() ? 0 : 1;
}

void net_done(void)
{
    fn_shutdown();
}

static void reset(struct net_stream *s)
{
    s->open = 0;
    s->rx_offset = 0;
    s->tx_offset = 0;
    s->rx_read = s->rx_write = s->rx_count = 0;
    s->rx_total = s->tx_total = s->polls = 0;
    s->last_error = FN_OK;
}

int net_open(struct net_stream *s, const char *host, unsigned port)
{
    fn_handle_t h = FN_INVALID_HANDLE;

    reset(s);
    s->last_error = fn_tcp_open(&h, host, (uint16_t)port);
    if (s->last_error != FN_OK)
        return 1;
    s->handle = h;
    s->open = 1;
    /* The connect is asynchronous and fn_info() does not report its
     * progress for TCP; a write made while it is still connecting returns
     * NOT_READY, which net_write() retries, and a failed connect surfaces
     * as an I/O error on that first write. */
    return 0;
}

void net_close(struct net_stream *s)
{
    if (s->open)
        fn_close(s->handle);
    s->open = 0;
}

int net_write(struct net_stream *s, const unsigned char *buf, unsigned len)
{
    int waited = 0;

    while (len > 0) {
        uint16_t written = 0;
        uint16_t part = len > READ_CHUNK ? READ_CHUNK : (uint16_t)len;
        uint8_t rc = fn_write(s->handle, s->tx_offset, buf, part, &written);

        if (rc == FN_ERR_NOT_READY || rc == FN_ERR_BUSY) {
            if (++waited > WRITE_WAIT_TICKS) {
                s->last_error = FN_ERR_TIMEOUT;
                return 1;
            }
            Delay(1);
            continue;
        }
        if (rc != FN_OK) {
            s->last_error = rc;
            return 1;
        }
        s->tx_offset += written;
        s->tx_total += written;
        buf += written;
        len -= written;
    }
    return 0;
}

int net_poll(struct net_stream *s)
{
    uint16_t got = 0;
    uint8_t flags = 0;
    uint16_t room = (uint16_t)(NET_RX_CAP - s->rx_count);
    uint8_t rc;
    unsigned i;

    if (!s->open)
        return -1;
    if (room == 0)
        return 0;               /* parsers are behind; let them catch up */
    if (room > READ_CHUNK)
        room = READ_CHUNK;
    ++s->polls;
    rc = fn_read(s->handle, s->rx_offset, chunk, room, &got, &flags);
    if (rc == FN_ERR_NOT_READY || rc == FN_ERR_BUSY)
        return 0;
    if (rc != FN_OK) {
        s->last_error = rc;
        return -1;
    }
    for (i = 0; i < got; ++i) {
        s->rx[s->rx_write] = chunk[i];
        if (++s->rx_write == NET_RX_CAP)
            s->rx_write = 0;
    }
    s->rx_count += got;
    s->rx_offset += got;
    s->rx_total += got;
    if ((flags & FN_READ_EOF) && got == 0) {
        s->last_error = FN_ERR_IO;  /* server closed the connection */
        return -1;
    }
    return got;
}

int net_get(struct net_stream *s, unsigned char *byte)
{
    if (s->rx_count == 0)
        return 0;
    *byte = s->rx[s->rx_read];
    if (++s->rx_read == NET_RX_CAP)
        s->rx_read = 0;
    --s->rx_count;
    return 1;
}

const char *net_error_text(const struct net_stream *s)
{
    return fn_error_string(s->last_error);
}
