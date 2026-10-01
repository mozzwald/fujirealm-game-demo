#include "login.h"
#include "identity.h"
#include "input.h"
#include "bf_proto.h"
#include "server_host_default.h"
#include <coco.h>
#include <fujinet-network.h>

#define PT_LOGIN_REQ 0xA0
#define PT_LOGIN_RESP 0xA1
#define PT_RESUME_REQ 0xA2
#define PT_RESUME_RESP 0xA3
#define LOGIN_OK 0

#define LOGIN_NET_MAX_READ 128
#define LOGIN_TICKS_TIMEOUT 300 /* ~5s at the 60Hz tick, one shot per attempt */

/* One request/response round trip: opens LOGIN_SERVER_PORT, sends a $BF
 * frame of req_type/req_payload, waits (bounded) for one $BF frame back,
 * closes either way. */
static unsigned char login_roundtrip(const char *host, unsigned char req_type,
                                     const unsigned char *req_payload,
                                     unsigned char req_payload_len,
                                     struct bf_packet *resp)
{
    char devicespec[64];
    unsigned char out[LOGIN_USERNAME_MAX + 6];
    unsigned char frame_len;
    unsigned char buf[LOGIN_NET_MAX_READ];
    struct bf_parser parser;
    uint16_t bytes_waiting;
    uint8_t conn_status;
    uint8_t err;
    int16_t got;
    unsigned int start_tick;
    unsigned char i;
    unsigned char found = 0;

    sprintf(devicespec, "N1:TCP://%s:%u/", host, LOGIN_SERVER_PORT);

    if (network_open(devicespec, 12, 0) != FN_ERR_OK) {
        network_close(devicespec);
        return 0;
    }

    frame_len = bf_build(out, req_type, req_payload, req_payload_len);
    if (network_write(devicespec, out, frame_len) != FN_ERR_OK) {
        network_close(devicespec);
        return 0;
    }

    bf_parser_init(&parser);
    start_tick = getTimer();

    while (!found &&
           (unsigned int)(getTimer() - start_tick) < LOGIN_TICKS_TIMEOUT) {
        if (network_status(devicespec, &bytes_waiting, &conn_status, &err) !=
            FN_ERR_OK) {
            break;
        }
        if (bytes_waiting == 0) {
            continue;
        }

        got = network_read_nb(devicespec, buf, LOGIN_NET_MAX_READ);
        if (got < 0) {
            break;
        }

        for (i = 0; i < (unsigned char)got && !found; ++i) {
            if (bf_parser_feed(&parser, buf[i], resp)) {
                found = 1;
            }
        }
    }

    network_close(devicespec);
    return found;
}

unsigned char login_identity(const char *host, char *username_out,
                             char *token_out)
{
    char name[LOGIN_USERNAME_MAX + 1];
    struct bf_packet resp;
    unsigned char req[LOGIN_USERNAME_MAX + 1];
    unsigned char len;
    unsigned char ulen;
    unsigned char tlen;
    unsigned char tries;
    const char *note = 0;

    if (identity_load(host, name, token_out)) {
        printf("Resume %s @ %s...\n", name, host);

        len = (unsigned char)strlen(token_out);
        req[0] = len;
        memcpy(&req[1], token_out, len);

        /* A new name can't reach an unreachable server either. */
        if (!login_roundtrip(host, PT_RESUME_REQ, req, (unsigned char)(len + 1),
                             &resp)) {
            printf("Server %s unreachable.\n", host);
            return 0;
        }
        if (resp.type == PT_RESUME_RESP && resp.payload_len >= 2 &&
            resp.payload[0] == LOGIN_OK) {
            ulen = resp.payload[1];
            if (ulen > LOGIN_USERNAME_MAX) {
                ulen = LOGIN_USERNAME_MAX;
            }
            memcpy(username_out, &resp.payload[2], ulen);
            username_out[ulen] = 0;
            printf("OK.\n");
            return 1;
        }
        printf("Resume fail.\n");
    }

    for (tries = 0; tries < 3; ++tries) {
        if (!input_name_entry(name, LOGIN_USERNAME_MAX, note)) {
            return 0;
        }

        printf("Login %s...\n", name);
        len = (unsigned char)strlen(name);
        req[0] = len;
        memcpy(&req[1], name, len);

        if (!login_roundtrip(host, PT_LOGIN_REQ, req, (unsigned char)(len + 1),
                             &resp)) {
            printf("Server %s unreachable.\n", host);
            return 0;
        }
        if (resp.type != PT_LOGIN_RESP || resp.payload_len < 2) {
            printf("Bad response.\n");
            return 0;
        }
        if (resp.payload[0] != LOGIN_OK) {
            printf("Name taken.\n");
            note = "Name taken. Try another.";
            continue;
        }

        tlen = resp.payload[1];
        if (tlen > LOGIN_TOKEN_MAX) {
            tlen = LOGIN_TOKEN_MAX;
        }
        memcpy(token_out, &resp.payload[2], tlen);
        token_out[tlen] = 0;
        strcpy(username_out, name);
        identity_store(host, username_out, token_out);
        printf("Login OK.\n");
        return 1;
    }

    printf("Too many tries.\n");
    return 0;
}
