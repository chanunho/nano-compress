import unittest

from nanocompress.target_size import next_bitrate, plan_size, within_cap


class PlanSizeTests(unittest.TestCase):
    def test_10mb_60s_one_audio_track(self):
        plan = plan_size(60.0, 10 * 1024 * 1024, 1)
        self.assertEqual(plan.budget_bytes, 9762242)
        self.assertEqual(plan.video_kbps, 1237)
        self.assertEqual(plan.audio_kbps, 64)

    def test_more_audio_tracks_lower_video_bitrate(self):
        one = plan_size(60.0, 10 * 1024 * 1024, 1)
        two = plan_size(60.0, 10 * 1024 * 1024, 2)
        self.assertLess(two.video_kbps, one.video_kbps)

    def test_impossible_target_raises(self):
        with self.assertRaises(ValueError):
            plan_size(600.0, 100 * 1024, 1)

    def test_invalid_inputs_raise(self):
        for args in ((0, 1024 * 1024, 1), (60, 0, 1), (60, 1024, -1)):
            with self.assertRaises(ValueError):
                plan_size(*args)


class RetryTests(unittest.TestCase):
    def test_within_cap(self):
        self.assertTrue(within_cap(100, 100))
        self.assertFalse(within_cap(101, 100))

    def test_next_bitrate_scales_down(self):
        self.assertEqual(next_bitrate(120, 100, 1000), 816)
