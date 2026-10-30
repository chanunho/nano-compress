import os, shutil, subprocess, tempfile, unittest
from nanocompress.verify import needs_h264_fallback, verify_output

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.clip = os.path.join(self.dir, "ok.mp4")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "1", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", self.clip,
        ], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_output_passes(self):
        result = verify_output(self.clip, 1.0, 1)
        self.assertTrue(result.ok, result.reasons)

    def test_missing_file_fails(self):
        result = verify_output(os.path.join(self.dir, "nope.mp4"), 1.0, 1)
        self.assertFalse(result.ok)
        self.assertIs(needs_h264_fallback(result), True)

    def test_corrupt_file_fails(self):
        bad = os.path.join(self.dir, "bad.mp4")
        with open(bad, "wb") as handle:
            handle.write(b"not a video")
        self.assertFalse(verify_output(bad, 1.0, 1).ok)

    def test_duration_mismatch_fails(self):
        self.assertFalse(verify_output(self.clip, 10.0, 1).ok)

    def test_audio_count_mismatch_fails(self):
        result = verify_output(self.clip, 1.0, 2)
        self.assertFalse(result.ok)
        self.assertTrue(any("audio" in reason for reason in result.reasons))
