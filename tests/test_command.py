import unittest

from nanocompress.settings import Options
from nanocompress.probe import MediaInfo, Subtitle
from nanocompress.command import (
    EncodeJob,
    EncodePlan,
    ProductEncodeJob,
    build_product_commands,
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
                is_hdr=False, is_dolby_vision=False,
                is_interlaced=False, audio_tracks=1, subtitles=())
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

    def test_target_width_rotated_anamorphic(self):
        m = media(width=320, height=240, rotation=90, sample_aspect_ratio="2:1")
        self.assertEqual(target_width(m, 240), 90)


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

    def test_hdr_mastering_metadata_passed_to_x265(self):
        m = media(
            is_hdr=True,
            color_transfer="smpte2084",
            color_primaries="bt2020",
            color_space="bt2020nc",
            master_display="G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1)",
            max_cll="1000,400",
        )
        cmd = build_command(job(media_info=m)).args
        self.assertIn("-x265-params", cmd)
        params = cmd[cmd.index("-x265-params") + 1]
        self.assertIn("master-display=", params)
        self.assertIn("max-cll=1000,400", params)


def product_job(media_info=None, **plan_kw):
    plan = dict(encoder="libx264", encoder_preset="veryfast", resolution=720,
                crf=26, video_kbps=None, audio_bitrate="64k",
                keep_hdr=False, keep_metadata=False, compatibility=False,
                target_bytes=None)
    plan.update(plan_kw)
    return ProductEncodeJob("in.mp4", "/tmp/out.mp4", "/tmp/passlog",
                            media_info or media(), EncodePlan(**plan))


class ProductCommandTests(unittest.TestCase):
    def test_sdr_default_strips_metadata_and_scales(self):
        m = media(width=1920, height=1080, sample_aspect_ratio="1:1")
        cmd = build_product_commands(product_job(m))[0].args
        filters = cmd[cmd.index("-vf") + 1]
        self.assertIn("scale=1280:720:flags=lanczos", filters)
        self.assertNotIn("zscale", filters)
        self.assertIn("-map_metadata", cmd)
        self.assertEqual(cmd[cmd.index("-map_metadata") + 1], "-1")
        self.assertIn("+faststart", cmd)

    def test_keep_metadata_maps_source_metadata(self):
        cmd = build_product_commands(product_job(keep_metadata=True))[0].args
        self.assertEqual(cmd[cmd.index("-map_metadata") + 1], "0")

    def test_hdr_default_tonemaps_to_sdr(self):
        m = media(is_hdr=True, color_transfer="smpte2084", color_primaries="bt2020")
        cmd = build_product_commands(product_job(m))[0].args
        self.assertIn("zscale", " ".join(cmd))
        self.assertIn("yuv420p", cmd)
        self.assertNotIn("-color_primaries", cmd)

    def test_keep_hdr_preserves_10bit_and_metadata(self):
        m = media(is_hdr=True, color_transfer="smpte2084", color_primaries="bt2020")
        cmd = build_product_commands(product_job(m, keep_hdr=True, encoder="libx265"))[0].args
        self.assertNotIn("zscale", " ".join(cmd))
        self.assertIn("yuv420p10le", cmd)
        self.assertIn("-color_primaries", cmd)
        self.assertIn("hvc1", cmd)

    def test_dolby_vision_always_tonemaps_and_warns(self):
        m = media(is_hdr=True, is_dolby_vision=True)
        result = build_product_commands(product_job(m, keep_hdr=True, encoder="libx265"))[0]
        self.assertIn("zscale", " ".join(result.args))
        self.assertTrue(any("Dolby Vision" in w for w in result.warnings))

    def test_compatibility_forces_cfr_30(self):
        cmd = build_product_commands(product_job(compatibility=True))[0].args
        self.assertIn("fps=30", cmd[cmd.index("-vf") + 1])

    def test_default_preserves_vfr_timestamps(self):
        cmd = build_product_commands(product_job())[0].args
        self.assertNotIn("fps=", " ".join(cmd))

    def test_hardware_bitrate_mode(self):
        cmd = build_product_commands(product_job(encoder="h264_nvenc", crf=None,
                                                 video_kbps=1000))[0].args
        self.assertIn("h264_nvenc", cmd)
        self.assertIn("-b:v", cmd)
        self.assertNotIn("-crf", cmd)
        self.assertNotIn("-preset", cmd)

    def test_target_size_uses_two_passes(self):
        commands = build_product_commands(product_job(crf=None, video_kbps=1237,
                                                      target_bytes=10 * 1024 * 1024))
        self.assertEqual(len(commands), 2)
        self.assertIn("-pass", commands[0].args)
        self.assertEqual(commands[0].args[commands[0].args.index("-pass") + 1], "1")
        self.assertIn("-f", commands[0].args)
        self.assertIn("null", commands[0].args)
        self.assertEqual(commands[1].args[commands[1].args.index("-pass") + 1], "2")

    def test_target_size_emits_software_preset(self):
        commands = build_product_commands(product_job(
            crf=None, video_kbps=1237, target_bytes=10 * 1024 * 1024,
            encoder_preset="slow",
        ))
        for command in commands:
            self.assertIn("-preset", command.args)
            self.assertEqual(
                command.args[command.args.index("-preset") + 1], "slow"
            )

    def test_maps_all_audio_and_text_subtitles(self):
        m = media(subtitles=(Subtitle(2, "subrip"), Subtitle(5, "hdmv_pgs_subtitle")))
        result = build_product_commands(product_job(m))[0]
        self.assertIn("0:a?", result.args)
        self.assertIn("0:2", result.args)
        self.assertNotIn("0:5", result.args)
        self.assertTrue(any("image-based" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
