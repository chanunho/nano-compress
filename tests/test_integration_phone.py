# tests/test_integration_phone.py
import json, os, shutil, subprocess, tempfile, unittest
from nanocompress.compress import CompressRequest, compress

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class PhoneIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _clip(self, name, extra=()):
        path = os.path.join(self.dir, name)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "2", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "10",
            "-pix_fmt", "yuv420p", "-c:a", "aac", *extra, path,
        ], check=True)
        return path

    def test_gps_metadata_is_stripped(self):
        src = self._clip("gps.mp4", ("-metadata", "location=+37.7-122.4/"))
        out = os.path.join(self.dir, "gps_small.mp4")
        result = compress(CompressRequest(src, out, profile="send", speed="smallest",
                                          codec="h264"))
        self.assertTrue(result.ok, result.error)
        tags = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                               "format_tags", "-of", "json", out],
                              capture_output=True, text=True, check=True).stdout
        self.assertNotIn("location", tags.lower())

    def test_target_size_is_never_exceeded(self):
        src = self._clip("cap.mp4")
        out = os.path.join(self.dir, "cap_small.mp4")
        result = compress(CompressRequest(src, out, profile="custom", target_mb=0.25))
        self.assertTrue(result.ok, result.error)
        self.assertLessEqual(os.path.getsize(out), int(0.25 * 1024 * 1024))

    def test_output_duration_matches_source_and_plays(self):
        src = self._clip("dur.mp4")
        out = os.path.join(self.dir, "dur_small.mp4")
        result = compress(CompressRequest(src, out, profile="send", codec="h264",
                                          speed="smallest"))
        self.assertTrue(result.ok, result.error)
        data = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format",
                                          "-show_streams", "-of", "json", out],
                                         capture_output=True, text=True,
                                         check=True).stdout)
        self.assertAlmostEqual(float(data["format"]["duration"]), 2.0, delta=1.0)
        self.assertTrue(any(s["codec_type"] == "video" for s in data["streams"]))
