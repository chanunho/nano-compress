import os
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
        outputs = sorted(os.path.relpath(j.output_path, os.path.join(self.root, "compressed")) for j in jobs)
        self.assertEqual(outputs, ["a_nc.mp4", "b_nc.mp4", "sub/c_nc.mp4"])

    def test_output_dir_pruned_from_discovery(self):
        out = os.path.join(self.root, "compressed")
        os.makedirs(out)
        open(os.path.join(out, "old.mp4"), "wb").close()
        jobs = plan_jobs(self.root, out, recursive=True, overwrite=False)
        self.assertFalse(any("old.mp4" in j.input_path for j in jobs))

    def test_collision_gets_numeric_suffix(self):
        open(os.path.join(self.root, "b.mp4"), "wb").close()
        jobs = plan_jobs(self.root, None, recursive=False, overwrite=False)
        names = sorted(os.path.basename(j.output_path) for j in jobs)
        self.assertIn("b_nc.mp4", names)
        self.assertIn("b_nc_1.mp4", names)


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


if __name__ == "__main__":
    unittest.main()
