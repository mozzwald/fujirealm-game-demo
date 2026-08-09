# FujiRealm -- top level. Each client has its own Makefile; this one delegates
# to them and hosts the server and test targets.
#
# Point a client at your server with SERVER_HOST (both clients take the same
# variable names), or set it once in the client's config.mk:
#
#   make SERVER_HOST=192.168.1.100
#   make SERVER_HOST=myhost.local HYBRID_SERVER_PORT=9000 LOGIN_SERVER_PORT=9010

HYBRID_SERVER_PORT ?= 9000
LOGIN_SERVER_PORT ?= 9010
MAKEOVERRIDES_PASS = SERVER_HOST=$(SERVER_HOST) \
	HYBRID_SERVER_PORT=$(HYBRID_SERVER_PORT) LOGIN_SERVER_PORT=$(LOGIN_SERVER_PORT)

.PHONY: all atari lynx atr nettest clean test test-server test-tools test-lynx \
	test-editor run-server run-login-server run-smoke-server run-bootstrap-server

all: atari lynx

atari:
	$(MAKE) -C atari8-client all

lynx:
	$(MAKE) -C lynx-client all

atr:
	$(MAKE) -C atari8-client atr

nettest:
	$(MAKE) -C atari8-client nettest

clean:
	$(MAKE) -C atari8-client clean
	$(MAKE) -C lynx-client clean

# --- tests ------------------------------------------------------------------

test: test-server test-tools test-lynx

test-server:
	python3 -m unittest discover -s server/tests -p 'test_*.py'

# The charsetter tests parse the assembled art out of the client source, which
# pulls in the generated includes, so the Atari client has to have been built.
test-tools: atari
	python3 -m unittest tools.test_charsetter tools.test_map_csv tools.test_server_host_default

test-lynx:
	$(MAKE) -C lynx-client test

# Needs node. The rest of the suite does not.
test-editor:
	cd tools/tile-editor && node --test tile-model.test.js lynx-model.test.js

# --- servers ----------------------------------------------------------------

# The game client bootstraps over TCP, then drops the connection and reconnects
# in realtime mode -- only hybrid_server handles that second phase.
run-server:
	python3 -m server.hybrid_server --port $(HYBRID_SERVER_PORT) --debug

run-login-server:
	python3 -m server.login_server --port $(LOGIN_SERVER_PORT) --debug

# The older byte-stream-only server, kept for exercising the bootstrap protocol
# in isolation.
run-bootstrap-server:
	python3 -m server.bootstrap_server --debug

# Minimal TCP server that accepts FujiNet's REGISTER and echoes a probe byte;
# for bringing up the netstream link before any game protocol is involved.
run-smoke-server:
	python3 -m server.netstream_smoke_server
