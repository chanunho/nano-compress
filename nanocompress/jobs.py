import os
from dataclasses import dataclass

VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".m4v",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".ts",
        ".flv",
        ".wmv",
        ".mpeg",
        ".mpg",
    }
)


@dataclass(frozen=True)
class PlannedJob:
    input_path: str
    output_path: str
    skip: bool = False
    reason: str = ""


def is_video_file(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


def default_output_for(input_path):
    return os.path.splitext(input_path)[0] + "_nc.mp4"


def _unique_path(path, used):
    if path not in used:
        return path
    stem, extension = os.path.splitext(path)
    index = 1
    while f"{stem}_{index}{extension}" in used:
        index += 1
    return f"{stem}_{index}{extension}"


def _plan_file(input_path, output_path, overwrite):
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)
    output = output_path or default_output_for(input_path)
    if os.path.realpath(output) == os.path.realpath(input_path):
        raise ValueError("output path must differ from the input path")
    skip = os.path.exists(output) and not overwrite
    return [PlannedJob(input_path, output, skip, "exists" if skip else "")]


def _iter_sources(root, recursive, output_dir):
    output_real = os.path.realpath(output_dir)
    if not recursive:
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name)
            if os.path.isfile(path) and is_video_file(path):
                yield path
        return
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(
            directory
            for directory in dirs
            if os.path.realpath(os.path.join(current, directory)) != output_real
        )
        for name in sorted(files):
            path = os.path.join(current, name)
            if is_video_file(path):
                yield path


def _plan_folder(input_path, output_path, recursive, overwrite):
    if not os.path.isdir(input_path):
        raise NotADirectoryError(input_path)
    output_dir = output_path or os.path.join(input_path, "compressed")
    root = os.path.realpath(input_path)
    jobs = []
    used = set()
    for source in _iter_sources(input_path, recursive, output_dir):
        relative = os.path.relpath(os.path.realpath(source), root)
        relative_output = os.path.splitext(relative)[0] + "_nc.mp4"
        output = os.path.join(output_dir, relative_output)
        output = _unique_path(output, used)
        used.add(output)
        skip = os.path.exists(output) and not overwrite
        jobs.append(PlannedJob(source, output, skip, "exists" if skip else ""))
    return jobs


def plan_jobs(input_path, output_path, *, recursive, overwrite):
    if os.path.isdir(input_path):
        return _plan_folder(input_path, output_path, recursive, overwrite)
    return _plan_file(input_path, output_path, overwrite)


class TempOutput:
    def __init__(self, final_path):
        self.final_path = final_path
        self.temp_path = final_path[:-4] + ".part.mp4"

    def __enter__(self):
        return self.temp_path

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            os.replace(self.temp_path, self.final_path)
        elif os.path.exists(self.temp_path):
            os.remove(self.temp_path)
        return False
