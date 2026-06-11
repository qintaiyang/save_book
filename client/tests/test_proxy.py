import unittest

from qidian_save.proxy import ProxyPool, parse_proxy_urls


class ProxyTests(unittest.TestCase):
    def test_parse_proxy_urls_accepts_repeated_and_comma_separated_values(self):
        urls = parse_proxy_urls([
            "http://one.example:8080,socks5://two.example:1080",
            "https://three.example:8443",
        ])
        self.assertEqual(urls, [
            "http://one.example:8080",
            "socks5://two.example:1080",
            "https://three.example:8443",
        ])

    def test_proxy_pool_rotates_after_configured_request_count(self):
        pool = ProxyPool(
            ["http://one.example:8080", "socks5://two.example:1080"],
            rotate_every=2,
        )
        selected = [pool.requests_proxies()["https"] for _ in range(4)]
        self.assertEqual(selected, [
            "http://one.example:8080",
            "http://one.example:8080",
            "socks5://two.example:1080",
            "socks5://two.example:1080",
        ])

    def test_empty_proxy_pool_uses_direct_connection(self):
        self.assertIsNone(ProxyPool([]).requests_proxies())


if __name__ == "__main__":
    unittest.main()
