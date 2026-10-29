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
        with open(bad, "wb") as handle:
            handle.write(b"not a video")
        result = run_job(PlannedJob(bad, os.path.join(self.dir, "bad_nc.mp4")), Options())
        self.assertFalse(result.ok)
        self.assertIn(bad, result.error)

    def test_rotated_anamorphic_source_has_correct_aspect(self):
        anamorphic = os.path.join(self.dir, "anamorphic.mp4")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24",
            "-t", "1", "-vf", "setsar=2/1", "-c:v", "libx264",
            "-preset", "ultrafast", "-pix_fmt", "yuv420p", anamorphic,
        ], check=True)
        rotated = os.path.join(self.dir, "rotated_anamorphic.mp4")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-display_rotation", "90", "-i", anamorphic, "-c", "copy", rotated,
        ], check=True)
        out = os.path.join(self.dir, "rotated_anamorphic_nc.mp4")
        result = run_job(PlannedJob(rotated, out),
                         Options(encoder="h264", resolution=240, preset="ultrafast"))
        self.assertTrue(result.ok, result.error)
        dimensions = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "default=noprint_wrappers=1", out,
        ], capture_output=True, text=True, check=True).stdout
        self.assertIn("width=90", dimensions)
        self.assertIn("height=240", dimensions)

    def test_preserves_multiple_audio_tracks_and_text_subtitles(self):
        subtitle = os.path.join(self.dir, "subs.srt")
        with open(subtitle, "w") as handle:
            handle.write("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
        multi = os.path.join(self.dir, "multi.mp4")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000",
            "-i", subtitle,
            "-t", "1", "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-c:s", "mov_text", multi,
        ], check=True)
        out = os.path.join(self.dir, "multi_nc.mp4")
        result = run_job(PlannedJob(multi, out),
                         Options(encoder="h264", resolution=144, preset="ultrafast"))
        self.assertTrue(result.ok, result.error)
        streams = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name",
            "-of", "default=noprint_wrappers=1", out,
        ], capture_output=True, text=True, check=True).stdout
        self.assertEqual(streams.count("codec_type=audio"), 2)
        self.assertIn("codec_name=mov_text", streams)

    def test_hdr_mastering_metadata_preserved(self):
        hdr = os.path.join(self.dir, "hdr.mp4")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=24", "-t", "1",
            "-c:v", "libx265",
            "-x265-params",
            "master-display=G(13250,34500)B(7500,3000)R(34000,16000)"
            "WP(15635,16450)L(10000000,1):max-cll=1000,400:repeat-headers=1",
            "-pix_fmt", "yuv420p10le",
            "-color_primaries", "bt2020", "-color_trc", "smpte2084",
            "-colorspace", "bt2020nc", hdr,
        ], check=True)
        out = os.path.join(self.dir, "hdr_nc.mp4")
        result = run_job(PlannedJob(hdr, out),
                         Options(encoder="hevc", resolution=144, preset="ultrafast"))
        self.assertTrue(result.ok, result.error)
        side_data = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_frames", "-read_intervals", "%+#1",
            "-show_entries", "frame=side_data_list",
            "-of", "default=noprint_wrappers=1", out,
        ], capture_output=True, text=True, check=True).stdout
        self.assertIn("Mastering display metadata", side_data)
        self.assertIn("Content light level metadata", side_data)


if __name__ == "__main__":
    unittest.main()
