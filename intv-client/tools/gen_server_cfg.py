#!/usr/bin/env python3
"""Generate server_cfg.bas: build-time server endpoint baked as ASCII DATA.

IntyBASIC has no string type and no preprocessor defines, so the endpoint the
other clients take from SERVER_HOST/config.mk arrives here as DATA byte
tables the client feeds to fn_putstr. The Makefile runs this whenever
config.mk changes, mirroring the "changing the host forces a relink" behavior
of the Atari and Lynx clients.

Usage: python3 tools/gen_server_cfg.py HOST GAME_PORT LOGIN_PORT > server_cfg.bas
"""

import sys


def emit(label, const, s):
    print("    CONST %s = %d" % (const, len(s)))
    print("%s:" % label)
    print("    DATA %s\t' \"%s\"" % (",".join(str(ord(c)) for c in s), s))


def main():
    host, game_port, login_port = sys.argv[1], sys.argv[2], sys.argv[3]
    if len(host) > 40:
        sys.exit("SERVER_HOST too long (max 40 chars)")
    if any(ord(c) < 33 or ord(c) > 126 or c == "," for c in host):
        sys.exit("SERVER_HOST must be printable ASCII without commas")

    print("' server_cfg.bas -- baked server endpoint (GENERATED FILE -- do not edit;")
    print("' set SERVER_HOST / HYBRID_SERVER_PORT / LOGIN_SERVER_PORT in config.mk)")
    emit("game_url", "GAME_URL_LEN", "N:TCP://%s:%s/" % (host, game_port))
    emit("login_url", "LOGIN_URL_LEN", "N:TCP://%s:%s/" % (host, login_port))
    emit("host_str", "HOST_LEN", host)


if __name__ == "__main__":
    main()
