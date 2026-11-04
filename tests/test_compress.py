import os, tempfile, unittest
from nanocompress.compress import CompressRequest, compress
from nanocompress.encoders import Encoder
from nanocompress.probe import MediaInfo
from nanocompress.verify import Verification

MEDIA = MediaInfo(duration=60.0, width=1920, height=1080, video_codec="hevc",
                  sample_aspect_ratio="1:1", rotation=0, color_transfer="bt709",
                  color_primaries="bt709", is_hdr=False, is_interlaced=False,
                  audio_tracks=1, subtitles=())


class CompressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.src = os.path.join(self.dir, "in.mp4")
        with open(self.src, "wb") as handle:
            handle.write(b"x" * (2 * 1024 * 1024))
        self.out = os.path.join(self.dir, "out.mp4")

    def tearDown(self):
        self.tmp.cleanup()

    def _request(self, **kw):
        base = dict(input_path=self.src, output_path=self.out, profile="send")
        base.update(kw)
        return CompressRequest(**base)

    def _runner(self, sizes):
        calls = []
        def run(args, duration, **kw):
            calls.append(args)
            if "-pass" in args and args[args.index("-pass") + 1] == "1":
                return 0
            path = args[-1]
            size = sizes.pop(0)
            with open(path, "wb") as handle:
                handle.write(b"x" * size)
            return 0
        return run, calls

    def test_output_equal_to_input_is_rejected(self):
        result = compress(self._request(output_path=self.src),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=lambda *a, **k: 0)
        self.assertFalse(result.ok)
        self.assertIn("differ", result.error.lower())

    def test_already_small_returns_original_without_encoding(self):
        run, calls = self._runner([])
        result = compress(self._request(profile="custom", target_mb=10),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run, verifier=lambda *a, **k: Verification(True, (), 60, "h264", 1))
        self.assertTrue(result.already_small)
        self.assertEqual(result.output_path, self.src)
        self.assertEqual(calls, [])

    def test_hard_cap_retries_and_never_exceeds(self):
        run, calls = self._runner([int(1.2 * 1024 * 1024), 900 * 1024])
        result = compress(self._request(profile="custom", target_mb=1),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run, verifier=lambda *a, **k: Verification(True, (), 60, "h264", 1))
        self.assertTrue(result.ok, result.error)
        self.assertLessEqual(result.output_size, 1024 * 1024)
        self.assertGreaterEqual(len(calls), 2)

    def test_failed_verification_falls_back_to_h264(self):
        run, calls = self._runner([900 * 1024, 900 * 1024])
        checked = []
        def verify(path, duration, audio, **kw):
            checked.append(path)
            return Verification(len(checked) > 1, (), 60, "h264", 1)
        result = compress(self._request(profile="storage"),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx265", "hevc", False),
                                            Encoder("libx264", "h264", False)),
                          runner=run, verifier=verify)
        self.assertTrue(result.ok, result.error)
        self.assertIn("libx264", " ".join(calls[-1]))

    def test_dry_run_returns_commands_and_writes_nothing(self):
        run, calls = self._runner([])
        result = compress(self._request(profile="custom", target_mb=1, dry_run=True),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run)
        self.assertTrue(result.ok)
        self.assertFalse(os.path.exists(self.out))
        self.assertEqual(calls, [])
        self.assertTrue(any("-pass" in cmd for cmd in result.planned_commands))

    def test_cancel_reports_error_and_removes_partial(self):
        from nanocompress.process import Cancelled
        def run(args, duration, **kw):
            raise Cancelled()
        result = compress(self._request(profile="send"),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run)
        self.assertFalse(result.ok)
        self.assertIn("cancel", result.error.lower())
        self.assertFalse(os.path.exists(self.out))
