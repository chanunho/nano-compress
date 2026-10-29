import os
import tempfile
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
    absolute_input = os.path.abspath(input_path)
    absolute_output = os.path.abspath(output_path or os.path.join(input_path, "compressed"))
    sources = list(_iter_sources(input_path, recursive, absolute_output))

    stem_counts = {}
    for source in sources:
        source_abs = os.path.abspath(source)
        key = (os.path.dirname(source_abs), os.path.splitext(os.path.basename(source_abs))[0])
        stem_counts[key] = stem_counts.get(key, 0) + 1

    jobs = []
    used = set()
    for source in sources:
        source_abs = os.path.abspath(source)
        name = os.path.basename(source_abs)
        stem, extension = os.path.splitext(name)
        key = (os.path.dirname(source_abs), stem)
        extension = extension.lstrip(".").lower()
        base = f"{stem}_{extension}" if stem_counts[key] > 1 else stem

        relative = os.path.relpath(source_abs, absolute_input)
        relative_dir = os.path.dirname(relative)
        relative_output = (
            os.path.join(relative_dir, f"{base}_nc.mp4")
            if relative_dir
            else f"{base}_nc.mp4"
        )
        output = os.path.normpath(os.path.join(absolute_output, relative_output))
        try:
            common = os.path.commonpath([os.path.abspath(output), absolute_output])
        except ValueError:
            common = None
        if common != absolute_output:
            raise ValueError(f"refusing to write outside the output folder: {output}")
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
        self.temp_path = None

    def __enter__(self):
        directory = os.path.dirname(os.path.abspath(self.final_path))
        os.makedirs(directory, exist_ok=True)
        stem = os.path.splitext(os.path.basename(self.final_path))[0]
        handle, path = tempfile.mkstemp(
            prefix=f"{stem}.", suffix=".part.mp4", dir=directory
        )
        os.close(handle)
        self.temp_path = path
        return path

    def __exit__(self, exc_type, exc, traceback):
        if self.temp_path is None:
            return False
        if exc_type is None:
            os.replace(self.temp_path, self.final_path)
        elif os.path.exists(self.temp_path):
            os.remove(self.temp_path)
        return False
