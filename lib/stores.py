import os
from pathlib import Path
from lib.util import NoSuchKey, save_to_s3, read_from_s3

class FileStore:
    def __init__(self, root):
        self.root = Path(root)

    def _path(self, path) -> Path:
        # An unmounted mountpoint looks like an empty directory; never write
        # into it, or the export lands on the local disk.
        if not self.root.is_dir():
            raise RuntimeError(f"Storage root does not exist: {self.root}")
        return self.root / str(path).removeprefix("/")

    def write(self, path, data, **_):
        path = self._path(path)
        if isinstance(data, str):
            data = data.encode()
        elif not isinstance(data, bytes):
            raise RuntimeError(f"Invalid argument type: {type(data)}")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        with open(tmp, "wb") as f:
            f.write(data)
            os.fsync(f.fileno())
        tmp.replace(path)

    def read(self, path) -> bytes:
        try:
            return self._path(path).read_bytes()
        except FileNotFoundError as err:
            raise NoSuchKey(*err.args)


class S3Store:
    def __init__(self, bucket_name):
        self.bucket_name = bucket_name

    def write(self, path, data, **kwargs):
        return save_to_s3(self.bucket_name, path, data, **kwargs)

    def read(self, path):
        return read_from_s3(self.bucket_name, path)
