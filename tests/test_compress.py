import os, tempfile, unittest
from dataclasses import replace
from nanocompress.compress import CompressRequest, compress
from nanocompress.encoders import Encoder
from nanocompress.probe import MediaInfo
from nanocompress.verify import Verification

MEDIA = MediaInfo(duration=60.0, width=1920, height=1080, video_codec="hevc",
                  sample_aspect_ratio="1:1", rotation=0, color_transfer="bt709",
                  color_primaries="bt709", is_hdr=False, is_interlaced=False,
                  audio_tracks=1, subtitles=())
HDR_MEDIA = replace(MEDIA, is_hdr=True, color_transfer="smpte2084",
                    color_primaries="bt2020")
SHORT_MEDIA = replace(MEDIA, duration=10.0)


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

    def test_runner_nonzero_stops_and_reports_failure(self):
        calls = []
        def run(args, duration, **kw):
            calls.append(args)
            return 1
        result = compress(self._request(profile="custom", target_mb=1),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run)
        self.assertFalse(result.ok)
        self.assertIn("exit status 1", result.error)
        self.assertEqual(len(calls), 1)
        self.assertFalse(os.path.exists(self.out))

    def test_command_error_detail_is_surfaced(self):
        from nanocompress.process import CommandError
        def run(args, duration, **kw):
            raise CommandError(1, "encoder exploded")
        result = compress(self._request(profile="send"),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run)
        self.assertFalse(result.ok)
        self.assertIn("encoder exploded", result.error)

    def test_hardware_failure_retries_with_software_encoder(self):
        calls = []
        def run(args, duration, **kw):
            calls.append(args)
            if "h264_nvenc" in args:
                return 1
            with open(args[-1], "wb") as handle:
                handle.write(b"x" * (900 * 1024))
            return 0
        result = compress(
            self._request(profile="send"),
            prober=lambda _: MEDIA,
            detector=lambda: (Encoder("h264_nvenc", "h264", True),
                              Encoder("libx264", "h264", False)),
            runner=run,
            verifier=lambda *a, **k: Verification(True, (), 60, "h264", 1),
        )
        self.assertTrue(result.ok, result.error)
        self.assertIn("libx264", calls[-1])
        self.assertTrue(any("h264_nvenc" in warning
                            for warning in result.warnings))

    def test_target_cap_never_returns_over_cap_original(self):
        with open(self.src, "wb") as handle:
            handle.write(b"x" * 1_059_061)
        run, calls = self._runner([1_018_880])
        result = compress(self._request(profile="custom", target_mb=1),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run,
                          verifier=lambda *a, **k: Verification(True, (), 60, "h264", 1))
        self.assertTrue(result.ok, result.error)
        self.assertFalse(result.already_small)
        self.assertLessEqual(result.output_size, 1024 * 1024)
        self.assertEqual(result.output_path, self.out)

    def test_target_cap_keeps_under_cap_output_near_source_size(self):
        with open(self.src, "wb") as handle:
            handle.write(b"x" * 1_059_061)
        run, calls = self._runner([1_040_000])
        result = compress(self._request(profile="custom", target_mb=1),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run,
                          verifier=lambda *a, **k: Verification(True, (), 60, "h264", 1))
        self.assertTrue(result.ok, result.error)
        self.assertFalse(result.already_small)
        self.assertLessEqual(result.output_size, 1024 * 1024)
        self.assertEqual(result.output_path, self.out)

    def test_resolution_reduction_emits_warning(self):
        run, calls = self._runner([1_200_000, 1_100_000, 900_000])
        result = compress(self._request(profile="custom", target_mb=1),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run,
                          verifier=lambda *a, **k: Verification(True, (), 60, "h264", 1))
        self.assertTrue(result.ok, result.error)
        self.assertLessEqual(result.output_size, 1024 * 1024)
        self.assertTrue(any("Reduced resolution from 720p to 540p" in warning
                            for warning in result.warnings))

    def test_target_verification_failure_falls_back_under_cap(self):
        run, calls = self._runner([200 * 1024, 300 * 1024, 200 * 1024])
        checked = []
        def verify(path, duration, audio, **kw):
            checked.append(path)
            return Verification(len(checked) > 1, (), 60, "h264", 1)
        result = compress(self._request(profile="custom", target_mb=1),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run, verifier=verify)
        self.assertTrue(result.ok, result.error)
        self.assertLessEqual(result.output_size, 1024 * 1024)
        self.assertEqual(result.output_path, self.out)
        self.assertTrue(any("Output failed verification" in warning
                            for warning in result.warnings))
        self.assertIn("libx264", calls[-1])
        self.assertIn("-pass", calls[-1])

    def test_target_size_reduces_audio_before_final_attempt(self):
        run, calls = self._runner([300 * 1024] * 3)
        result = compress(self._request(profile="custom", target_mb=0.25),
                          prober=lambda _: SHORT_MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run,
                          verifier=lambda *a, **k: Verification(True, (), 10, "h264", 1))
        self.assertFalse(result.ok)
        self.assertTrue(any("audio bitrate" in warning and "48k" in warning
                            for warning in result.warnings))
        self.assertIn("-b:a 48k", " ".join(calls[-1]))

    def test_target_size_failure_names_audio_and_suggests_larger_cap(self):
        run, calls = self._runner([300 * 1024] * 3)
        result = compress(self._request(profile="custom", target_mb=0.25),
                          prober=lambda _: SHORT_MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run,
                          verifier=lambda *a, **k: Verification(True, (), 10, "h264", 1))
        self.assertFalse(result.ok)
        self.assertIn("could not fit under 0.25 MB", result.error)
        self.assertIn("with 1 audio track(s)", result.error)
        self.assertIn("try a larger cap", result.error)

    def test_prober_failure_returns_error(self):
        def boom(_):
            raise RuntimeError("cannot read input")
        result = compress(self._request(),
                          prober=boom,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=lambda *a, **k: 0)
        self.assertFalse(result.ok)
        self.assertIn("cannot read input", result.error)
        self.assertFalse(os.path.exists(self.out))

    def test_keep_hdr_forces_hevc_and_10bit(self):
        run, calls = self._runner([900 * 1024])
        result = compress(self._request(profile="send", keep_hdr=True),
                          prober=lambda _: HDR_MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),
                                            Encoder("libx265", "hevc", False)),
                          runner=run,
                          verifier=lambda *a, **k: Verification(True, (), 60, "hevc", 1))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.encoder, "libx265")
        command = " ".join(calls[-1])
        self.assertIn("-c:v libx265", command)
        self.assertIn("yuv420p10le", command)
        self.assertNotIn("zscale", command)
        self.assertTrue(any("HEVC" in warning for warning in result.warnings))

    def test_keep_hdr_with_hard_cap_disables_hdr(self):
        run, calls = self._runner([900 * 1024])
        result = compress(self._request(profile="custom", target_mb=1,
                                        keep_hdr=True),
                          prober=lambda _: HDR_MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),
                                            Encoder("libx265", "hevc", False)),
                          runner=run,
                          verifier=lambda *a, **k: Verification(True, (), 60, "h264", 1))
        self.assertTrue(result.ok, result.error)
        command = " ".join(calls[-1])
        self.assertIn("zscale", command)
        self.assertNotIn("yuv420p10le", command)
        self.assertTrue(any("HDR was disabled to meet the size cap" in warning
                            for warning in result.warnings))


