import os
import shutil
import subprocess
import tempfile
import unittest

from nanocompress.settings import Options
from nanocompress.jobs import PlannedJob
from nanocompress.runner import JobResult, human_size, format_summary, run_job

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


class HumanSizeTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(999), "999 B")
        self.assertEqual(human_size(1536), "1.5 KB")
        self.assertEqual(human_size(5 * 1024 * 1024), "5.0 MB")


class SummaryTests(unittest.TestCase):
    def test_summary_reports_totals(self):
        results = [
            JobResult("a.mp4", "a_nc.mp4", 1000, 400, True),
            JobResult("b.mp4", "b_nc.mp4", 2000, 1000, True),
            JobResult("c.mp4", "c_nc.mp4", 500, 0, False, error="boom"),
            JobResult("d.mp4", "d_nc.mp4", 300, 300, True, skipped=True),
        ]
        text = format_summary(results)
        self.assertIn("2 encoded", text)
        self.assertIn("1 skipped", text)
        self.assertIn("1 failed", text)
        self.assertIn("boom", text)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class RunJobIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.src = os.path.join(self.dir, "src.mp4")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "2", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", self.src,
        ], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, overwrite=False):
        out = os.path.join(self.dir, "out.mp4")
        return run_job(PlannedJob(self.src, out), Options(encoder="h264", resolution=144,
                                                          preset="ultrafast", overwrite=overwrite))

    def test_encodes_playable_output(self):
        result = self._run()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.original_size, os.path.getsize(self.src))
        self.assertGreater(result.output_size, 0)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                "-show_entries", "stream=codec_name,height",
                                "-of", "default=noprint_wrappers=1", result.output_path],
                               capture_output=True, text=True, check=True).stdout
        self.assertIn("codec_name=h264", probe)
        self.assertIn("height=144", probe)

    def test_faststart_moov_before_mdat(self):
        result = self._run()
        data = open(result.output_path, "rb").read()
        self.assertLess(data.find(b"moov"), data.find(b"mdat"))

    def test_rotated_source_is_not_sideways(self):
        rotated = os.path.join(self.dir, "rotated.mp4")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-display_rotation", "90", "-i", self.src, "-c", "copy", rotated,
        ], check=True)
        out = os.path.join(self.dir, "rotated_nc.mp4")
        result = run_job(PlannedJob(rotated, out),
                         Options(encoder="h264", resolution=144, preset="ultrafast"))
        self.assertTrue(result.ok, result.error)
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:stream_side_data=rotation",
            "-of", "default=noprint_wrappers=1", out,
        ], capture_output=True, text=True, check=True).stdout
        self.assertIn("width=108", probe)
        self.assertIn("height=144", probe)
        self.assertNotIn("rotation=", probe)

    def test_corrupt_input_reports_error(self):
        bad = os.path.join(self.dir, "bad.mp4")
        open(bad, "wb").write(b"not a video")
        result = run_job(PlannedJob(bad, os.path.join(self.dir, "bad_nc.mp4")), Options())
        self.assertFalse(result.ok)
        self.assertTrue(result.error)


if __name__ == "__main__":
    unittest.main()
