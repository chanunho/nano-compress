import unittest

from nanocompress.presets import Profile, resolve_profile


class ResolveProfileTests(unittest.TestCase):
    def test_send_defaults_to_fast_h264_720p(self):
        p = resolve_profile("send")
        self.assertEqual((p.speed, p.codec, p.resolution), ("fast", "h264", 720))
        self.assertIsNone(p.target_bytes)

    def test_discord_is_a_10mb_cap(self):
        self.assertEqual(resolve_profile("discord").target_bytes, 10 * 1024 * 1024)

    def test_email_is_a_25mb_cap(self):
        self.assertEqual(resolve_profile("email").target_bytes, 25 * 1024 * 1024)

    def test_storage_is_balanced_hevc_480p(self):
        p = resolve_profile("storage")
        self.assertEqual((p.speed, p.codec, p.resolution), ("balanced", "hevc", 480))

    def test_custom_requires_a_target(self):
        with self.assertRaises(ValueError):
            resolve_profile("custom")
        self.assertEqual(resolve_profile("custom", target_mb=7.5).target_bytes, 7864320)

    def test_target_mb_overrides_the_profile_cap(self):
        self.assertEqual(resolve_profile("discord", target_mb=1).target_bytes, 1024 * 1024)

    def test_speed_and_codec_overrides(self):
        p = resolve_profile("send", speed="smallest", codec="hevc")
        self.assertEqual((p.speed, p.codec), ("smallest", "hevc"))

    def test_unknown_profile_speed_and_codec_fail(self):
        for kwargs in ({"name": "nope"}, {"name": "send", "speed": "warp"},
                       {"name": "send", "codec": "av1"}):
            with self.assertRaises(ValueError):
                resolve_profile(**kwargs)

    def test_negative_target_fails(self):
        with self.assertRaises(ValueError):
            resolve_profile("custom", target_mb=-1)


if __name__ == "__main__":
    unittest.main()
