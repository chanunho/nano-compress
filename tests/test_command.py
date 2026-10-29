import unittest

from nanocompress.settings import Options
from nanocompress.probe import MediaInfo, Subtitle
from nanocompress.command import (
    EncodeJob,
    should_tonemap,
    parse_sar,
    target_width,
    build_filters,
    resolve_pix_fmt,
    build_command,
)


def media(**kw):
    base = dict(duration=60.0, width=842, height=456, video_codec="hevc",
                sample_aspect_ratio="2105:2109", rotation=0,
                color_transfer="bt709", color_primaries="bt709",
                is_hdr=False, is_interlaced=False, audio_tracks=1, subtitles=())
    base.update(kw)
    return MediaInfo(**base)


def job(media_info=None, options=None, out="/tmp/out.mp4"):
    return EncodeJob("in.mp4", out, media_info or media(), options or Options())


class WidthTests(unittest.TestCase):
    def test_parse_sar(self):
        self.assertEqual(parse_sar("1:1"), 1.0)
        self.assertAlmostEqual(parse_sar("2105:2109"), 2105 / 2109)
        self.assertEqual(parse_sar(""), 1.0)
        self.assertEqual(parse_sar("0:1"), 1.0)

    def test_target_width_square(self):
        self.assertEqual(target_width(media(width=1920, height=1080, sample_aspect_ratio="1:1"), 240), 426)

    def test_target_width_anamorphic_preserves_display_aspect(self):
        self.assertEqual(target_width(media(width=842, height=456, sample_aspect_ratio="2105:2109"), 240), 442)

    def test_target_width_accounts_for_rotation(self):
        self.assertEqual(target_width(media(width=160, height=120, rotation=90, sample_aspect_ratio="1:1"), 144), 108)


class FilterTests(unittest.TestCase):
    def test_default_filters_scale_and_square_pixels(self):
        f = build_filters(media(), Options())
        self.assertIn("scale=442:240:flags=lanczos", f)
        self.assertIn("setsar=1", f)

    def test_denoise_levels(self):
        self.assertNotIn("hqdn3d", build_filters(media(), Options(denoise="off")))
        self.assertIn("hqdn3d=1.5:1.5:6:6", build_filters(media(), Options(denoise="light")))
        self.assertIn("hqdn3d=3:3:9:9", build_filters(media(), Options(denoise="medium")))
        self.assertIn("hqdn3d=6:6:12:12", build_filters(media(), Options(denoise="strong")))

    def test_fps_added_when_requested(self):
        self.assertIn("fps=24", build_filters(media(), Options(fps=24)))
        self.assertNotIn("fps=", build_filters(media(), Options()))

    def test_interlaced_sources_deinterlaced(self):
        self.assertIn("yadif", build_filters(media(is_interlaced=True), Options()))
        self.assertNotIn("yadif", build_filters(media(is_interlaced=False), Options()))

    def test_hdr_preserved_by_default_no_tonemap(self):
        m = media(is_hdr=True, color_transfer="smpte2084", color_primaries="bt2020")
        self.assertFalse(should_tonemap(m, Options()))
        self.assertNotIn("tonemap", build_filters(m, Options()))

    def test_tonemap_flag_converts_hdr(self):
        m = media(is_hdr=True, color_transfer="smpte2084", color_primaries="bt2020")
        self.assertTrue(should_tonemap(m, Options(tonemap=True)))
        self.assertIn("zscale", build_filters(m, Options(tonemap=True)))
        self.assertIn("tonemap", build_filters(m, Options(tonemap=True)))

    def test_h264_hdr_autotonemaps(self):
        m = media(is_hdr=True, color_transfer="smpte2084", color_primaries="bt2020")
        self.assertTrue(should_tonemap(m, Options(encoder="h264")))

    def test_tonemap_on_sdr_is_noop(self):
        self.assertFalse(should_tonemap(media(), Options(tonemap=True)))


class PixelFormatTests(unittest.TestCase):
    def test_sdr_default_is_8bit(self):
        self.assertEqual(resolve_pix_fmt(media(), Options()), "yuv420p")

    def test_hdr_preserved_is_10bit(self):
        self.assertEqual(resolve_pix_fmt(media(is_hdr=True), Options()), "yuv420p10le")

    def test_10bit_flag(self):
        self.assertEqual(resolve_pix_fmt(media(), Options(ten_bit=True)), "yuv420p10le")

    def test_tonemap_default_is_8bit(self):
        m = media(is_hdr=True)
        self.assertEqual(resolve_pix_fmt(m, Options(tonemap=True)), "yuv420p")

    def test_tonemap_plus_10bit(self):
        m = media(is_hdr=True)
        self.assertEqual(resolve_pix_fmt(m, Options(tonemap=True, ten_bit=True)), "yuv420p10le")


class CommandTests(unittest.TestCase):
    def test_hevc_defaults(self):
        cmd = build_command(job()).args
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("libx265", cmd)
        self.assertIn("hvc1", cmd)
        self.assertIn("28", cmd)
        self.assertIn("+faststart", cmd)
        self.assertIn("slow", cmd)

    def test_h264_has_no_hvc1_tag(self):
        cmd = build_command(job(options=Options(encoder="h264"))).args
        self.assertIn("libx264", cmd)
        self.assertNotIn("hvc1", cmd)

    def test_maps_all_audio_and_text_subtitles(self):
        m = media(subtitles=(Subtitle(2, "subrip"), Subtitle(5, "hdmv_pgs_subtitle")))
        result = build_command(job(media_info=m))
        self.assertIn("0:a?", result.args)
        self.assertIn("0:2", result.args)
        self.assertNotIn("0:5", result.args)
        self.assertIn("mov_text", result.args)
        self.assertTrue(any("image-based" in w for w in result.warnings))

    def test_hdr_color_metadata_preserved(self):
        m = media(is_hdr=True, color_transfer="smpte2084", color_primaries="bt2020")
        cmd = build_command(job(media_info=m)).args
        self.assertIn("bt2020", cmd)
        self.assertIn("smpte2084", cmd)
        self.assertIn("yuv420p10le", cmd)

    def test_tonemap_emits_warning_for_h264_hdr(self):
        m = media(is_hdr=True)
        result = build_command(job(media_info=m, options=Options(encoder="h264")))
        self.assertTrue(any("tone-map" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
