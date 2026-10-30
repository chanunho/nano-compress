import unittest

from nanocompress.encoders import (
    Encoder,
    choose_encoder,
    detect_encoders,
    encoder_preset,
    parse_encoders,
)

SAMPLE = """
 V....D libx264              libx264 H.264 (codec h264)
 V....D libx265              libx265 H.265 (codec hevc)
 V....D h264_nvenc           NVIDIA NVENC H.264 encoder
 V....D hevc_videotoolbox    VideoToolbox H.265 encoder
"""

EXTENDED = SAMPLE + """
 V....D h264_vaapi           VAAPI H.264 encoder
 V....D h264_qsv             Intel Quick Sync H.264 encoder
 V....D hevc_qsv             Intel Quick Sync H.265 encoder
 V....D h264_amf             AMD AMF H.264 encoder
"""


class ParseTests(unittest.TestCase):
    def test_parses_software_and_hardware(self):
        names = {e.name for e in parse_encoders(SAMPLE)}
        self.assertIn("libx264", names)
        self.assertIn("h264_nvenc", names)
        self.assertIn("hevc_videotoolbox", names)

    def test_flags_hardware(self):
        by_name = {e.name: e for e in parse_encoders(SAMPLE)}
        self.assertFalse(by_name["libx264"].hardware)
        self.assertTrue(by_name["h264_nvenc"].hardware)

    def test_maps_codecs(self):
        by_name = {e.name: e for e in parse_encoders(EXTENDED)}
        self.assertEqual(by_name["libx264"].codec, "h264")
        self.assertEqual(by_name["libx265"].codec, "hevc")
        self.assertEqual(by_name["h264_nvenc"].codec, "h264")
        self.assertEqual(by_name["hevc_videotoolbox"].codec, "hevc")
        self.assertTrue(by_name["h264_vaapi"].hardware)

    def test_ignores_non_encoder_lines(self):
        text = "Encoders:\n ======\n V....D libx264  libx264 H.264\n"
        self.assertEqual([e.name for e in parse_encoders(text)], ["libx264"])

    def test_skips_legend_lines_from_real_ffmpeg_output(self):
        text = """Encoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 .F.... = Frame-level multithreading
 ..S... = Slice-level multithreading
 ...X.. = Codec is experimental
 ....B. = Supports draw_horiz_band
 .....D = Supports direct rendering method 1
 ------
 V....D libx264              libx264 H.264 (codec h264)
 V....D h264_nvenc           NVIDIA NVENC H.264 encoder
"""
        self.assertEqual(
            [e.name for e in parse_encoders(text)],
            ["libx264", "h264_nvenc"],
        )


class DetectTests(unittest.TestCase):
    def test_runs_ffmpeg_encoders_listing(self):
        calls = []

        class Result:
            stdout = SAMPLE

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return Result()

        encoders = detect_encoders(runner=runner)

        self.assertEqual(calls[0][0], ["ffmpeg", "-hide_banner", "-encoders"])
        self.assertTrue(calls[0][1]["capture_output"])
        self.assertTrue(calls[0][1]["text"])
        self.assertTrue(calls[0][1]["check"])
        self.assertEqual({e.name for e in encoders}, {e.name for e in parse_encoders(SAMPLE)})


class ChooseTests(unittest.TestCase):
    def setUp(self):
        self.available = parse_encoders(SAMPLE)

    def test_fast_prefers_hardware(self):
        self.assertEqual(choose_encoder("h264", "fast", self.available, platform="linux"),
                         "h264_nvenc")

    def test_smallest_never_uses_hardware(self):
        self.assertEqual(choose_encoder("hevc", "smallest", self.available, platform="darwin"),
                         "libx265")

    def test_allow_hardware_false_falls_back_to_software(self):
        self.assertEqual(choose_encoder("h264", "fast", self.available,
                                        platform="linux", allow_hardware=False),
                         "libx264")

    def test_no_usable_encoder_raises(self):
        with self.assertRaises(RuntimeError):
            choose_encoder("h264", "fast", (), platform="linux")

    def test_vaapi_is_not_selected(self):
        available = parse_encoders(EXTENDED)
        self.assertEqual(choose_encoder("h264", "fast", available, platform="linux"),
                         "h264_nvenc")

    def test_qsv_used_when_nvenc_missing(self):
        available = tuple(e for e in parse_encoders(EXTENDED) if "nvenc" not in e.name)
        self.assertEqual(choose_encoder("h264", "balanced", available, platform="linux"),
                         "h264_qsv")

    def test_windows_prefers_nvenc_then_qsv_then_amf(self):
        available = parse_encoders(EXTENDED)
        self.assertEqual(choose_encoder("h264", "fast", available, platform="win32"),
                         "h264_nvenc")
        no_nvenc = tuple(e for e in available if "nvenc" not in e.name)
        self.assertEqual(choose_encoder("h264", "fast", no_nvenc, platform="win32"),
                         "h264_qsv")
        amf_only = tuple(e for e in available if e.name in ("libx264", "h264_amf"))
        self.assertEqual(choose_encoder("h264", "fast", amf_only, platform="win32"),
                         "h264_amf")

    def test_darwin_does_not_use_nvenc(self):
        available = parse_encoders(SAMPLE)
        self.assertEqual(choose_encoder("h264", "fast", available, platform="darwin"),
                         "libx264")

    def test_falls_back_to_software_when_hardware_misses_codec(self):
        available = (Encoder("libx265", "hevc", False),)
        self.assertEqual(choose_encoder("hevc", "fast", available, platform="linux"),
                         "libx265")

    def test_missing_software_fallback_raises(self):
        available = (Encoder("h264_nvenc", "h264", True),)
        with self.assertRaises(RuntimeError):
            choose_encoder("h264", "smallest", available, platform="linux")


class PresetTests(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(encoder_preset("fast", "h264"), "veryfast")
        self.assertEqual(encoder_preset("balanced", "hevc"), "medium")
        self.assertEqual(encoder_preset("smallest", "hevc"), "slow")

    def test_fast_hevc_is_fast(self):
        self.assertEqual(encoder_preset("fast", "hevc"), "fast")


if __name__ == "__main__":
    unittest.main()
