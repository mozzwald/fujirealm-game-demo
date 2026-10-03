/*
 * netprobe -- measure the FujiNet NIO TCP path the Amiga client depends on.
 *
 *   netprobe [host [port]]        default fujinet.online 9000
 *
 * Opens TCP through fujinet-nio.device, sends the server's smoke probe byte
 * (0x42, echoed by hybrid_server before a session is classified), and times
 * the echo, then times a run of empty fn_read() polls: each one is a full
 * FujiBus exchange over the serial link, which bounds how often the game can
 * look for packets.  Times are in 1/50 s ticks from DateStamp().
 */
#include <stdio.h>
#include <stdlib.h>

#include <dos/dos.h>
#include <proto/dos.h>

#include "fujinet-nio.h"

#define SMOKE_PROBE 0x42
#define POLLS 50

static long ticks_now(void)
{
	struct DateStamp ds;

	DateStamp(&ds);
	return ds.ds_Minute * 60L * 50L + ds.ds_Tick;
}

int main(int argc, char **argv)
{
	const char *host = argc > 1 ? argv[1] : "fujinet.online";
	unsigned port = argc > 2 ? (unsigned)atoi(argv[2]) : 9000;
	fn_handle_t h = FN_INVALID_HANDLE;
	uint8_t probe = SMOKE_PROBE, buf[64], flags, rc;
	uint16_t n, written;
	long t0, t1;
	uint32_t rx_off = 0;   /* TCP sessions need sequential stream offsets */
	int i, empty = 0, errs = 0;

	if (fn_init() != FN_OK || !fn_is_ready()) {
		printf("netprobe: FujiNet NIO not available\n");
		return RETURN_FAIL;
	}
	t0 = ticks_now();
	rc = fn_tcp_open(&h, host, port);
	t1 = ticks_now();
	printf("open %s:%u rc=%d (%s) %ld ticks\n", host, port, (int)rc,
	       fn_error_string(rc), t1 - t0);
	if (rc != FN_OK)
		return RETURN_ERROR;

	t0 = ticks_now();
	rc = fn_write(h, 0, &probe, 1, &written);
	printf("write rc=%d written=%d\n", (int)rc, (int)written);
	for (i = 0; i < 500; ++i) {
		n = 0;
		rc = fn_read(h, rx_off, buf, sizeof buf, &n, &flags);
		if (rc == FN_OK && n > 0) {
			rx_off += n;
			break;
		}
		if (rc != FN_OK && rc != FN_ERR_NOT_READY && rc != FN_ERR_BUSY) {
			printf("read rc=%d (%s)\n", (int)rc, fn_error_string(rc));
			break;
		}
		Delay(1);
	}
	t1 = ticks_now();
	printf("echo: %d byte(s) first=%02x after %d polls, %ld ticks\n", (int)n,
	       n ? buf[0] : 0, i, t1 - t0);

	t0 = ticks_now();
	for (i = 0; i < POLLS; ++i) {
		n = 0;
		rc = fn_read(h, rx_off, buf, sizeof buf, &n, &flags);
		if (rc == FN_ERR_NOT_READY || (rc == FN_OK && n == 0))
			++empty;
		else if (rc == FN_OK)
			rx_off += n;
		else
			++errs;
	}
	t1 = ticks_now();
	printf("%d polls: %d empty, %d errors, %ld ticks (%ld ms each)\n", POLLS,
	       empty, errs, t1 - t0, (t1 - t0) * 20L / POLLS);

	fn_close(h);
	fn_shutdown();
	return RETURN_OK;
}
