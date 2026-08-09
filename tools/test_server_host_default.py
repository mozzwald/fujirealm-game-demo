"""Tests for generated FujiRealm client connection defaults."""

import unittest

from tools.write_server_host_default import parse_port, render_config


class ServerConnectionDefaultsTest(unittest.TestCase):
    def test_renders_host_hybrid_port_and_login_port(self):
        config = render_config("game.example", 12345, 23456)

        self.assertIn("HYBRID_SERVER_PORT = 12345", config)
        self.assertIn("LOGIN_SERVER_PORT = 23456", config)
        self.assertIn("NETSTREAM_PORT_SWAPPED = $3930", config)
        self.assertIn("dta 103,97,109,101,46,101,120,97,109,112,108,101", config)
        self.assertIn("dta 58,50,51,52,53,54,47", config)

    def test_default_hybrid_port_has_expected_netstream_byte_order(self):
        config = render_config("localhost", 9000, 9010)

        self.assertIn("NETSTREAM_PORT_SWAPPED = $2823", config)
        self.assertIn("dta 58,57,48,49,48,47", config)

    def test_rejects_invalid_ports(self):
        for value in ("0", "65536", "abc"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_port(value, "TEST_PORT")


if __name__ == "__main__":
    unittest.main()
