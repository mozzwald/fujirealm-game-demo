#ifndef FUJIREALM_AMIGA_IDENTITY_H
#define FUJIREALM_AMIGA_IDENTITY_H

/* The player's login identity, cached across runs as the same
 * "<username>,<token>,<host>" record the Lynx client keeps in a FujiNet
 * appkey.  The Amiga keeps it in a file instead; a record issued by a
 * different server is rejected, so switching servers logs in afresh. */

#define NAME_MAX 8
#define TOKEN_MAX 12

struct identity {
    char name[NAME_MAX + 1];
    char token_ascii[TOKEN_MAX + 1];
    unsigned long token;
};

/* Parse a record for `host`; 1 if it is valid. Pure, host-testable. */
int identity_parse(struct identity *id, const char *record, unsigned len,
                   const char *host);
/* Format a record into out (at least 64 bytes); returns its length. */
unsigned identity_format(const struct identity *id, const char *host, char *out);
/* Token digits -> value; 0 means no valid token. */
unsigned long identity_token_value(const char *digits);

#ifdef __AMIGA__
int identity_load(struct identity *id, const char *path, const char *host);
int identity_save(const struct identity *id, const char *path, const char *host);
#endif

#endif
