#include <string.h>

#include "identity.h"

unsigned long identity_token_value(const char *digits)
{
    unsigned long value = 0;

    for (; *digits; ++digits) {
        if (*digits < '0' || *digits > '9')
            return 0;
        value = value * 10 + (unsigned long)(*digits - '0');
    }
    return value;
}

int identity_parse(struct identity *id, const char *record, unsigned len,
                   const char *host)
{
    unsigned i = 0, j = 0, hl = strlen(host);

    /* Name: printable ASCII, the server's own rule, and never a comma. */
    while (i < len && record[i] != ',') {
        if (j >= NAME_MAX || record[i] < 32 || record[i] > 126)
            return 0;
        id->name[j++] = record[i++];
    }
    if (j == 0 || i >= len)
        return 0;
    id->name[j] = '\0';
    ++i;
    j = 0;
    while (i < len && record[i] >= '0' && record[i] <= '9' && j < TOKEN_MAX)
        id->token_ascii[j++] = record[i++];
    id->token_ascii[j] = '\0';
    if (j == 0 || i >= len || record[i++] != ',')
        return 0;
    /* The rest must be exactly this host (trailing newline allowed). */
    if (len - i < hl || memcmp(record + i, host, hl) != 0)
        return 0;
    i += hl;
    while (i < len && (record[i] == '\n' || record[i] == '\r' || record[i] == 0))
        ++i;
    if (i != len)
        return 0;
    id->token = identity_token_value(id->token_ascii);
    return id->token != 0;
}

unsigned identity_format(const struct identity *id, const char *host, char *out)
{
    unsigned n = 0, k;

    for (k = 0; id->name[k]; ++k)
        out[n++] = id->name[k];
    out[n++] = ',';
    for (k = 0; id->token_ascii[k]; ++k)
        out[n++] = id->token_ascii[k];
    out[n++] = ',';
    for (k = 0; host[k] && n < 62; ++k)
        out[n++] = host[k];
    out[n++] = '\n';
    out[n] = '\0';
    return n;
}

#ifdef __AMIGA__
#include <dos/dos.h>
#include <proto/dos.h>

int identity_load(struct identity *id, const char *path, const char *host)
{
    char buf[80];
    BPTR fh = Open((UBYTE *)path, MODE_OLDFILE);
    LONG n;

    if (!fh)
        return 0;
    n = Read(fh, buf, sizeof(buf));
    Close(fh);
    return n > 0 && identity_parse(id, buf, (unsigned)n, host);
}

int identity_save(const struct identity *id, const char *path, const char *host)
{
    char buf[80];
    unsigned n = identity_format(id, host, buf);
    BPTR fh = Open((UBYTE *)path, MODE_NEWFILE);
    LONG w;

    if (!fh)
        return 0;
    w = Write(fh, buf, (LONG)n);
    Close(fh);
    return w == (LONG)n;
}
#endif
