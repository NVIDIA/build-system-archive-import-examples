import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Make the repo root importable so we can load parse_redist directly.
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import parse_redist


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_parse_artifact_uses_pwd_path_join():
    """Cached archive under <cwd>/<component>/<platform> must be found.

    Regression for a path-join bug: the existence check concatenated
    `pwd + filename` without a separator, so the cached archive was never
    found and `fetch_file` was always invoked.
    """
    original_cwd = os.getcwd()
    original_archives = parse_redist.ARCHIVES.copy()
    fetch_calls = []

    def fake_fetch(full_path, filename):
        fetch_calls.append((full_path, filename))

    original_fetch_file = parse_redist.fetch_file
    parse_redist.fetch_file = fake_fetch

    tmpdir = tempfile.mkdtemp()
    try:
        os.chdir(tmpdir)
        parse_redist.ARCHIVES.clear()

        component = "cuda_cccl"
        platform = "linux-x86_64"
        parse_redist.ARCHIVES[platform] = []
        filename = "cccl-v1.tar.xz"
        pwd = os.path.join(tmpdir, component, platform)
        os.makedirs(pwd, exist_ok=True)
        archive_path = os.path.join(pwd, filename)
        archive_data = b"fake archive data"
        with open(archive_path, "wb") as f:
            f.write(archive_data)

        size = len(archive_data)
        checksum = _sha256(Path(archive_path))
        manifest = {
            component: {
                platform: {
                    "relative_path": "/redist/" + filename,
                    "size": str(size),
                    "sha256": checksum,
                }
            }
        }
        parent = "https://example.com"

        parse_redist.parse_artifact(
            parent,
            manifest,
            component,
            platform,
            retrieve=True,
            integrity=True,
            validate=True,
        )

        assert not fetch_calls, f"fetch_file was called unexpectedly: {fetch_calls}"
        assert archive_path in parse_redist.ARCHIVES[platform]
    finally:
        parse_redist.fetch_file = original_fetch_file
        parse_redist.ARCHIVES.clear()
        parse_redist.ARCHIVES.update(original_archives)
        os.chdir(original_cwd)
        shutil.rmtree(tmpdir, ignore_errors=True)
