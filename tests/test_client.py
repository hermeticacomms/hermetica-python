import email.message
import io
import unittest
import urllib.error
from unittest import mock

from hermetica import Client, HermeticaError
from hermetica.client import _retry_after


def http_error(code, body="", retry_after=None):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://api.example.com/x", code, "err", headers, io.BytesIO(body.encode()))


class RetryTest(unittest.TestCase):
    def run_with(self, answers, **opts):
        """Calls a POST with urlopen answering from answers; returns (result or error, seen requests, sleeps)."""
        seen, sleeps = [], []

        def urlopen(req, timeout):
            seen.append(req)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return io.BytesIO(answer.encode())

        with mock.patch("urllib.request.urlopen", urlopen), mock.patch("time.sleep", sleeps.append):
            try:
                out = Client("hm_sk_test", base_url="https://api.example.com", **opts).post_v1_events(body={"a": 1})
            except (HermeticaError, OSError) as e:
                out = e
        return out, seen, sleeps

    def test_retries_5xx_429_and_network_errors_with_the_same_key(self):
        out, seen, sleeps = self.run_with([http_error(503, retry_after="2"), http_error(429), urllib.error.URLError("reset"), '{"ok":true}'])
        self.assertEqual(out, {"ok": True})
        self.assertEqual(len(seen), 4)
        self.assertEqual(len({r.get_header("Idempotency-key") for r in seen}), 1)
        self.assertTrue(seen[0].get_header("Idempotency-key"))
        self.assertEqual([r.data for r in seen], [b'{"a": 1}'] * 4)
        self.assertEqual(sleeps[0], 2.0)
        self.assertTrue(0 <= sleeps[1] < 0.5 and 0 <= sleeps[2] < 1.0)

    def test_gives_up_after_max_retries(self):
        out, seen, _ = self.run_with([http_error(502, "Bad gateway") for _ in range(2)], max_retries=1)
        self.assertIsInstance(out, HermeticaError)
        self.assertEqual((out.status, out.code, out.message), (502, "http_error", "Bad gateway"))
        self.assertEqual(len(seen), 2)

    def test_does_not_retry_4xx(self):
        out, seen, sleeps = self.run_with([http_error(404, '{"error":{"code":"not_found","message":"No"}}'), '{}'])
        self.assertEqual((out.status, out.code), (404, "not_found"))
        self.assertEqual((len(seen), sleeps), (1, []))

    def test_max_retries_zero_disables_retries(self):
        out, seen, _ = self.run_with([urllib.error.URLError("down")], max_retries=0)
        self.assertIsInstance(out, urllib.error.URLError)
        self.assertEqual(len(seen), 1)

    def test_retry_after_parsing(self):
        self.assertEqual(_retry_after("3"), 3.0)
        self.assertEqual(_retry_after("-1"), 0.0)
        self.assertEqual(_retry_after("Wed, 21 Oct 2015 07:28:00 GMT"), 0.0)
        self.assertIsNone(_retry_after("soon"))
        self.assertIsNone(_retry_after(None))


if __name__ == "__main__":
    unittest.main()
