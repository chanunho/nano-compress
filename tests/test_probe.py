import os
import shutil
import tempfile
import unittest

from nanocompress.probe import (
    is_hdr_color,
    is_interlaced_field_order,
    parse_rotation,
    parse_media_info,
    parse_master_display,
    parse_max_cll,
    probe,
)


def make_probe_json(*, transfer="bt709", primaries="bt709", field_order="progressive",
                    rotate=None, codec="hevc", subs=None):
    video = {
        "codec_type": "video", "codec_name": codec, "width": 842, "height": 456,
        "sample_aspect_ratio": "2105:2109",
        "color_transfer": transfer, "color_primaries": primaries,
        "field_order": field_order,
    }
    if rotate is not None:
        video["side_data_list"] = [{"side_data_type": "Display Matrix", "rotation": rotate}]
    streams = [video, {"codec_type": "audio", "codec_name": "aac"}]
    streams.extend(subs or [])
    return {"format": {"duration": "99.5"}, "streams": streams}


class ProbeHelperTests(unittest.TestCase):
    def test_hdr_transfers(self):
        self.assertTrue(is_hdr_color("smpte2084", "bt2020"))
        self.assertTrue(is_hdr_color("arib-std-b67", "bt2020"))

    def test_hdr_wide_gamut_without_hdr_transfer(self):
        self.assertTrue(is_hdr_color("bt2020-10", "bt2020"))

    def test_sdr_is_not_hdr(self):
        self.assertFalse(is_hdr_color("bt709", "bt709"))

    def test_interlaced_field_orders(self):
        self.assertTrue(is_interlaced_field_order("tt"))
        self.assertTrue(is_interlaced_field_order("bb"))
        self.assertFalse(is_interlaced_field_order("progressive"))
        self.assertFalse(is_interlaced_field_order(""))

    def test_parse_rotation_from_side_data(self):
        self.assertEqual(parse_rotation({"side_data_list": [{"rotation": -90}]}), 270)

    def test_parse_rotation_from_tag(self):
        self.assertEqual(parse_rotation({"tags": {"rotate": "90"}}), 90)

    def test_parse_rotation_default(self):
        self.assertEqual(parse_rotation({}), 0)

    def test_parse_rotation_malformed_side_data_falls_back(self):
        stream = {"side_data_list": [{"rotation": "N/A"}], "tags": {"rotate": "180"}}
        self.assertEqual(parse_rotation(stream), 180)
        self.assertEqual(parse_rotation({"side_data_list": [{"rotation": "N/A"}]}), 0)


class SideDataTests(unittest.TestCase):
    def test_parse_master_display(self):
        side_data = {
            "side_data_type": "Mastering display metadata",
            "red_x": "34000/50000", "red_y": "16000/50000",
            "green_x": "13250/50000", "green_y": "34500/50000",
            "blue_x": "7500/50000", "blue_y": "3000/50000",
            "white_point_x": "15635/50000", "white_point_y": "16450/50000",
            "min_luminance": "1/10000", "max_luminance": "10000000/10000",
        }
        self.assertEqual(
            parse_master_display(side_data),
            "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1)",
        )

    def test_parse_master_display_missing(self):
        self.assertEqual(parse_master_display({}), "")

    def test_parse_max_cll(self):
        self.assertEqual(parse_max_cll({"max_content": 1000, "max_average": 400}), "1000,400")
        self.assertEqual(parse_max_cll({}), "")


class ParseMediaInfoTests(unittest.TestCase):
    def test_parses_sdr_media(self):
        info = parse_media_info(make_probe_json())
        self.assertAlmostEqual(info.duration, 99.5)
        self.assertEqual((info.width, info.height), (842, 456))
        self.assertEqual(info.sample_aspect_ratio, "2105:2109")
        self.assertEqual(info.audio_tracks, 1)
        self.assertFalse(info.is_hdr)
        self.assertFalse(info.is_interlaced)
        self.assertEqual(info.rotation, 0)

    def test_detects_hdr_and_rotation(self):
        info = parse_media_info(make_probe_json(transfer="smpte2084", primaries="bt2020", rotate=-90))
        self.assertTrue(info.is_hdr)
        self.assertEqual(info.rotation, 270)
        self.assertEqual(info.color_transfer, "smpte2084")

    def test_detects_interlaced(self):
        self.assertTrue(parse_media_info(make_probe_json(field_order="tt")).is_interlaced)

    def test_parses_subtitles(self):
        subs = [
            {"index": 2, "codec_type": "subtitle", "codec_name": "subrip"},
            {"index": 3, "codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle"},
        ]
        info = parse_media_info(make_probe_json(subs=subs))
        self.assertEqual([(s.index, s.codec) for s in info.subtitles],
                         [(2, "subrip"), (3, "hdmv_pgs_subtitle")])

    def test_parses_color_space(self):
        data = make_probe_json()
        data["streams"][0]["color_space"] = "bt2020nc"
        self.assertEqual(parse_media_info(data).color_space, "bt2020nc")


@unittest.skipUnless(shutil.which("ffprobe"), "ffprobe not available")
class ProbeErrorTests(unittest.TestCase):
    def test_error_includes_path(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = os.path.join(directory, "bad.mp4")
            with open(bad, "wb") as handle:
                handle.write(b"not a video")
            with self.assertRaises(RuntimeError) as caught:
                probe(bad)
            self.assertIn(bad, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
