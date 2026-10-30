import os
import sys
import tempfile
import threading
import time
import unittest

from nanocompress.process import (
    Cancelled,
    Progress,
    _with_progress_args,
    run_with_progress,
)

FAKE = """
import sys, time
for pct in (10, 50, 100):
    print(f"out_time_ms={pct * 1000000}", flush=True)
    print(f"speed=1.0x", flush=True)
    print(f"progress={'end' if pct == 100 else 'continue'}", flush=True)
    time.sleep(0.01)
"""

SLOW = """
import time
time.sleep(30)
"""

MICROSECONDS = """
import time
print("out_time_us=2500000", flush=True)
print("speed=2.0x", flush=True)
print("progress=continue", flush=True)
print("out_time_us=5000000", flush=True)
print("speed=N/A", flush=True)
print("progress=end", flush=True)
"""

MALFORMED = """
import time
print("garbage", flush=True)
print("out_time_ms=not-a-number", flush=True)
print("speed=", flush=True)
print("out_time_ms=5000000", flush=True)
print("progress=continue", flush=True)
"""

EXIT_CODE = """
raise SystemExit(3)
"""


class CommandBuildingTests(unittest.TestCase):
    def test_progress_flags_follow_executable(self):
        self.assertEqual(
            _with_progress_args(["ffmpeg", "-i", "in"]),
            ["ffmpeg", "-progress", "pipe:1", "-nostats", "-i", "in"],
        )

    def test_progress_flags_follow_script_for_interpreters(self):
        self.assertEqual(
            _with_progress_args([sys.executable, "fake.py"]),
            [sys.executable, "fake.py", "-progress", "pipe:1", "-nostats"],
        )


class ProgressTests(unittest.TestCase):
    def _script(self, body):
        path = os.path.join(tempfile.mkdtemp(), "fake.py")
        with open(path, "w") as handle:
            handle.write(body)
        return [sys.executable, path]

    def test_reports_percentages(self):
        seen = []
        code = run_with_progress(self._script(FAKE), 100.0,
                                 progress=lambda p: seen.append(round(p.percent)))
        self.assertEqual(code, 0)
        self.assertEqual(seen, [10, 50, 100])

    def test_cancel_raises_and_stops_the_process(self):
        event = threading.Event()
        threading.Timer(0.2, event.set).start()
        with self.assertRaises(Cancelled):
            run_with_progress(self._script(SLOW), 100.0, cancel=event)

    def test_supports_microseconds_and_speed(self):
        seen = []
        code = run_with_progress(
            self._script(MICROSECONDS), 10.0,
            progress=lambda p: seen.append(
                (round(p.percent, 1), round(p.seconds, 1), p.speed)
            ),
        )
        self.assertEqual(code, 0)
        self.assertEqual(seen, [(25.0, 2.5, "2.0x"), (50.0, 5.0, "N/A")])

    def test_ignores_malformed_lines(self):
        seen = []
        code = run_with_progress(
            self._script(MALFORMED), 10.0,
            progress=lambda p: seen.append(round(p.percent)),
        )
        self.assertEqual(code, 0)
        self.assertEqual(seen, [50])

    def test_zero_duration_reports_zero_percent(self):
        seen = []
        code = run_with_progress(
            self._script(FAKE), 0.0,
            progress=lambda p: seen.append(p.percent),
        )
        self.assertEqual(code, 0)
        self.assertEqual(seen, [0.0, 0.0, 0.0])

    def test_returns_child_exit_code(self):
        self.assertEqual(run_with_progress(self._script(EXIT_CODE), 1.0), 3)

    def test_progress_is_frozen_dataclass(self):
        with self.assertRaises(Exception):
            Progress(percent=1.0, seconds=1.0, speed="1.0x").percent = 2.0


if __name__ == "__main__":
    unittest.main()
