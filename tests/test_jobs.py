import os
import shutil
import tempfile
import unittest

from nanocompress.jobs import (
    is_video_file,
    default_output_for,
    plan_jobs,
    TempOutput,
)


class NamingTests(unittest.TestCase):
    def test_video_extensions(self):
        self.assertTrue(is_video_file("a.MP4"))
        self.assertTrue(is_video_file("a.mkv"))
        self.assertFalse(is_video_file("a.txt"))

    def test_default_output(self):
        self.assertEqual(default_output_for("/vids/movie.mp4"), "/vids/movie_nc.mp4")
        self.assertEqual(default_output_for("/vids/movie.MKV"), "/vids/movie_nc.mp4")


class PlanFileModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.src = os.path.join(self.dir, "movie.mp4")
        open(self.src, "wb").close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_output_path(self):
        jobs = plan_jobs(self.src, None, recursive=False, overwrite=False)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].output_path, os.path.join(self.dir, "movie_nc.mp4"))
        self.assertFalse(jobs[0].skip)

    def test_existing_output_is_skipped(self):
        open(os.path.join(self.dir, "movie_nc.mp4"), "wb").close()
        jobs = plan_jobs(self.src, None, recursive=False, overwrite=False)
        self.assertTrue(jobs[0].skip)

    def test_overwrite_plans_encode(self):
        open(os.path.join(self.dir, "movie_nc.mp4"), "wb").close()
        jobs = plan_jobs(self.src, None, recursive=False, overwrite=True)
        self.assertFalse(jobs[0].skip)

    def test_refuses_to_overwrite_input(self):
        with self.assertRaises(ValueError):
            plan_jobs(self.src, self.src, recursive=False, overwrite=True)


class PlanFolderModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for rel in ("a.mp4", "b.mkv", "note.txt", "sub/c.mp4"):
            p = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_non_recursive_ignores_subdirs_and_nonvideo(self):
        jobs = plan_jobs(self.root, None, recursive=False, overwrite=False)
        names = sorted(os.path.basename(j.output_path) for j in jobs)
        self.assertEqual(names, ["a_nc.mp4", "b_nc.mp4"])

    def test_recursive_mirrors_tree(self):
        jobs = plan_jobs(self.root, None, recursive=True, overwrite=False)
        output_root = os.path.join(self.root, "compressed")
        outputs = sorted(
            os.path.normpath(os.path.relpath(j.output_path, output_root))
            for j in jobs
        )
        expected = sorted(
            ["a_nc.mp4", "b_nc.mp4", os.path.join("sub", "c_nc.mp4")]
        )
        self.assertEqual(outputs, expected)

    def test_output_dir_pruned_from_discovery(self):
        out = os.path.join(self.root, "compressed")
        os.makedirs(out)
        open(os.path.join(out, "old.mp4"), "wb").close()
        jobs = plan_jobs(self.root, out, recursive=True, overwrite=False)
        self.assertFalse(any("old.mp4" in j.input_path for j in jobs))

    def test_same_stem_uses_stable_extension_suffix(self):
        open(os.path.join(self.root, "b.mp4"), "wb").close()
        jobs = plan_jobs(self.root, None, recursive=False, overwrite=False)
        mapping = {
            os.path.basename(j.input_path): os.path.basename(j.output_path)
            for j in jobs
        }
        self.assertEqual(mapping["b.mkv"], "b_mkv_nc.mp4")
        self.assertEqual(mapping["b.mp4"], "b_mp4_nc.mp4")

    def test_new_same_stem_input_is_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "a.mkv"), "wb").close()
            first = plan_jobs(directory, None, recursive=False, overwrite=False)[0]
            self.assertEqual(os.path.basename(first.output_path), "a_nc.mp4")
            os.makedirs(os.path.dirname(first.output_path))
            open(first.output_path, "wb").close()

            open(os.path.join(directory, "a.avi"), "wb").close()
            jobs = plan_jobs(directory, None, recursive=False, overwrite=False)
            mapping = {
                os.path.basename(j.input_path): j
                for j in jobs
                if os.path.basename(j.input_path) in ("a.avi", "a.mkv")
            }
            self.assertEqual(os.path.basename(mapping["a.avi"].output_path), "a_avi_nc.mp4")
            self.assertEqual(os.path.basename(mapping["a.mkv"].output_path), "a_mkv_nc.mp4")
            self.assertFalse(mapping["a.avi"].skip)
            self.assertFalse(mapping["a.mkv"].skip)

    def test_symlinked_file_does_not_escape_output_dir(self):
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, True)
        external = os.path.join(outside, "outside.mp4")
        open(external, "wb").close()
        link = os.path.join(self.root, "link.mp4")
        try:
            os.symlink(external, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks are unavailable here: {exc}")

        jobs = plan_jobs(self.root, None, recursive=False, overwrite=False)
        planned = next(j for j in jobs if os.path.basename(j.input_path) == "link.mp4")
        output_root = os.path.realpath(os.path.join(self.root, "compressed"))
        output_real = os.path.realpath(planned.output_path)
        self.assertTrue(
            output_real.startswith(output_root + os.sep),
            f"{output_real} escapes {output_root}",
        )


class TempOutputTests(unittest.TestCase):
    def test_renames_on_success(self):
        with tempfile.TemporaryDirectory() as d:
            final = os.path.join(d, "out.mp4")
            with TempOutput(final) as tmp:
                self.assertTrue(tmp.endswith(".part.mp4"))
                open(tmp, "wb").close()
            self.assertTrue(os.path.exists(final))
            self.assertFalse(os.path.exists(tmp))

    def test_cleans_up_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            final = os.path.join(d, "out.mp4")
            tmp = None
            with self.assertRaises(RuntimeError):
                with TempOutput(final) as tmp:
                    open(tmp, "wb").close()
                    raise RuntimeError("boom")
            self.assertFalse(os.path.exists(final))
            self.assertFalse(os.path.exists(tmp))

    def test_temp_never_collides_with_input_or_existing_part_file(self):
        with tempfile.TemporaryDirectory() as d:
            final = os.path.join(d, "foo.mp4")
            possible_input = os.path.join(d, "foo.part.mp4")
            with open(possible_input, "wb") as handle:
                handle.write(b"original")
            with TempOutput(final) as tmp:
                self.assertNotEqual(os.path.abspath(tmp), os.path.abspath(possible_input))
                self.assertNotEqual(os.path.abspath(tmp), os.path.abspath(final))
                open(tmp, "wb").close()
            self.assertTrue(os.path.exists(possible_input))
            with open(possible_input, "rb") as handle:
                self.assertEqual(handle.read(), b"original")


if __name__ == "__main__":
    unittest.main()
