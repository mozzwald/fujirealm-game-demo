/* Host tests for the Amiga client's portable code (identity records).
 * The shared protocol modules are covered by lynx-client/tools/host_tests.c. */
#include <stdio.h>
#include <string.h>

#include "identity.h"

static int failures;

#define CHECK(cond) do { if (!(cond)) { \
    printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); ++failures; } } while (0)

static int parse(struct identity *id, const char *rec, const char *host)
{
    return identity_parse(id, rec, (unsigned)strlen(rec), host);
}

int main(void)
{
    struct identity id, back;
    char buf[80];
    unsigned n;

    CHECK(parse(&id, "AMIGA1,123456,fujinet.online\n", "fujinet.online"));
    CHECK(strcmp(id.name, "AMIGA1") == 0 && id.token == 123456UL);
    CHECK(parse(&id, "AMIGA1,123456,fujinet.online", "fujinet.online"));
    /* A token from another server must not be reused. */
    CHECK(!parse(&id, "AMIGA1,123456,localhost\n", "fujinet.online"));
    CHECK(!parse(&id, "AMIGA1,123456,fujinet.onlinex", "fujinet.online"));
    CHECK(!parse(&id, "AMIGA1,123456", "fujinet.online"));    /* pre-host record */
    CHECK(!parse(&id, ",123456,fujinet.online", "fujinet.online"));
    CHECK(!parse(&id, "TOOLONGNAME,1,fujinet.online", "fujinet.online"));
    CHECK(!parse(&id, "AMIGA1,0,fujinet.online", "fujinet.online"));
    CHECK(!parse(&id, "AMIGA1,,fujinet.online", "fujinet.online"));
    CHECK(identity_token_value("4294967295") == 4294967295UL);
    CHECK(identity_token_value("12a") == 0);

    strcpy(id.name, "ZED");
    strcpy(id.token_ascii, "987");
    n = identity_format(&id, "fujinet.online", buf);
    CHECK(n == strlen("ZED,987,fujinet.online\n"));
    CHECK(identity_parse(&back, buf, n, "fujinet.online"));
    CHECK(strcmp(back.name, "ZED") == 0 && back.token == 987UL);

    printf(failures ? "%d FAILED\n" : "all host tests passed\n", failures);
    return failures != 0;
}
