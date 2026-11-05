import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "compressor.py")
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def run_cli(*args, cwd=None):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd,
                          capture_output=True, text=True)


def make_clip(path, seconds=1):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=24,noise=alls=30:allf=t",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast",
        "-qp", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", path,
    ], check=True)


class CliBasicTests(unittest.TestCase):
    def test_help(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--resolution", result.stdout)
        self.assertIn("--tonemap", result.stdout)

    def test_invalid_crf_exits_2(self):
        result = run_cli("in.mp4", "out.mp4", "-c", "99")
        self.assertEqual(result.returncode, 2)
        self.assertIn("crf", result.stderr.lower())

    def test_missing_input_has_clear_message(self):
        result = run_cli("definitely-missing.mp4")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not found", result.stderr.lower())


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class CliIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_prints_command_without_encoding(self):
        src = os.path.join(self.dir, "a.mp4")
        make_clip(src)
        out = os.path.join(self.dir, "a_nc.mp4")
        result = run_cli(src, out, "--dry-run", "-e", "h264")
        self.assertEqual(result.returncode, 0)
        self.assertIn("ffmpeg", result.stdout)
        self.assertFalse(os.path.exists(out))

    def test_single_file_creates_output(self):
        src = os.path.join(self.dir, "a.mp4")
        make_clip(src)
        result = run_cli(src, "-r", "144", "-e", "h264", "-p", "ultrafast")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "a_nc.mp4")))

    def test_batch_continues_after_corrupt_file(self):
        make_clip(os.path.join(self.dir, "good.mp4"))
        with open(os.path.join(self.dir, "bad.mp4"), "wb") as handle:
            handle.write(b"nope")
        result = run_cli(self.dir, "-r", "144", "-e", "h264", "-p", "ultrafast")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "compressed", "good_nc.mp4")))
        self.assertIn("fail", result.stdout.lower())


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class ProductCliTests(unittest.TestCase):
    def test_dry_run_custom_cap_prints_two_passes_and_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.mp4")
            make_clip(src, seconds=3)
            out = os.path.join(tmp, "a_small.mp4")
            result = run_cli(src, out, "--profile", "custom", "--target-size", "0.3",
                             "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("-pass", result.stdout)
            self.assertIn("planned", result.stdout.lower())
            self.assertFalse(os.path.exists(out))

    def test_storage_profiles_uses_hevc(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.mp4")
            make_clip(src)
            result = run_cli(src, "--profile", "storage", "--dry-run")
            self.assertIn("libx265", result.stdout)

    def test_smallest_speed_uses_slow_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.mp4")
            make_clip(src)
            result = run_cli(src, "--profile", "send", "--speed", "smallest", "--dry-run")
            self.assertIn("slow", result.stdout)


if __name__ == "__main__":
    unittest.main()
