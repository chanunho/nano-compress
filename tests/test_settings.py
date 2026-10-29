import unittest

from nanocompress.settings import Options, resolve_crf, validate_options


class SettingsTests(unittest.TestCase):
    def test_named_quality_maps_per_encoder(self):
        self.assertEqual(resolve_crf(Options(encoder="hevc", quality="small")), 32)
        self.assertEqual(resolve_crf(Options(encoder="hevc", quality="balanced")), 28)
        self.assertEqual(resolve_crf(Options(encoder="hevc", quality="quality")), 24)
        self.assertEqual(resolve_crf(Options(encoder="h264", quality="small")), 29)
        self.assertEqual(resolve_crf(Options(encoder="h264", quality="balanced")), 25)
        self.assertEqual(resolve_crf(Options(encoder="h264", quality="quality")), 21)

    def test_explicit_crf_overrides_quality(self):
        self.assertEqual(resolve_crf(Options(quality="small", crf=19)), 19)

    def test_valid_options_pass(self):
        validate_options(Options())

    def test_invalid_resolution_rejected(self):
        with self.assertRaises(ValueError):
            validate_options(Options(resolution=999))

    def test_invalid_quality_rejected(self):
        with self.assertRaises(ValueError):
            validate_options(Options(quality="tiny"))

    def test_crf_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            validate_options(Options(crf=52))

    def test_h264_with_10bit_rejected(self):
        with self.assertRaises(ValueError):
            validate_options(Options(encoder="h264", ten_bit=True))

    def test_non_positive_fps_rejected(self):
        with self.assertRaises(ValueError):
            validate_options(Options(fps=0))

    def test_invalid_denoise_rejected(self):
        with self.assertRaises(ValueError):
            validate_options(Options(denoise="extreme"))

    def test_invalid_audio_bitrate_rejected(self):
        with self.assertRaises(ValueError):
            validate_options(Options(audio_bitrate="loud"))


if __name__ == "__main__":
    unittest.main()
