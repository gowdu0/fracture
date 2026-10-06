"""The shipped example must be complete even when the checkout is valid."""

import io
import shutil
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import check_release


def write_sdist(path, *, missing=None, special=None, duplicate=None):
    prefix = path.name.removesuffix(".tar.gz")
    with tarfile.open(path, "w:gz") as archive:
        for name in check_release.EXAMPLE_FILES:
            if name == missing:
                continue
            content = f"# shipped {name}\n".encode()
            member = tarfile.TarInfo(f"{prefix}/examples/{name}")
            if name == special:
                member.type = tarfile.SYMTYPE
                member.linkname = "../../checkout/examples/order_app.py"
                archive.addfile(member)
            else:
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
                if name == duplicate:
                    archive.addfile(member, io.BytesIO(content))
        # Unrelated archive content must never be copied or interpreted as a path.
        member = tarfile.TarInfo("../../unwanted.py")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))


def test_reads_only_required_shipped_files(tmp_path):
    sdist = tmp_path / "fracture_recovery-0.1.0.tar.gz"
    write_sdist(sdist)
    contents = check_release.read_sdist_examples(sdist)
    assert contents == {
        name: f"# shipped {name}\n".encode() for name in check_release.EXAMPLE_FILES
    }
    assert not (tmp_path / "unwanted.py").exists()


@pytest.mark.parametrize("missing", ["__init__.py", "order_adapter.py"])
def test_missing_shipped_example_file(tmp_path, missing):
    sdist = tmp_path / "fracture_recovery-0.1.0.tar.gz"
    write_sdist(sdist, missing=missing)
    with pytest.raises(ValueError, match=missing):
        check_release.read_sdist_examples(sdist)


@pytest.mark.parametrize("missing", ["__init__.py", "order_adapter.py"])
def test_valid_checkout_cannot_mask_incomplete_sdist(tmp_path, monkeypatch, missing):
    root = tmp_path / "checkout"
    (root / "dist").mkdir(parents=True)
    shutil.copytree(Path(__file__).resolve().parents[1] / "examples", root / "examples")
    assert all((root / "examples" / name).is_file() for name in check_release.EXAMPLE_FILES)
    (root / "pyproject.toml").write_text("[project]\n")
    (root / "dist/fracture_recovery-0.1.0-py3-none-any.whl").write_bytes(b"unused")
    write_sdist(root / "dist/fracture_recovery-0.1.0.tar.gz", missing=missing)
    monkeypatch.setattr(check_release, "__file__", str(root / "scripts/check_release.py"))
    monkeypatch.setattr("sys.argv", ["check_release", "--output", str(tmp_path / "evidence")])
    run = Mock()
    monkeypatch.setattr(check_release, "run", run)
    with pytest.raises(ValueError, match=missing):
        check_release.main()
    run.assert_not_called()  # Validation fails before either installation can begin.


def test_required_example_link_is_rejected(tmp_path):
    sdist = tmp_path / "fracture_recovery-0.1.0.tar.gz"
    write_sdist(sdist, special="order_app.py")
    with pytest.raises(ValueError, match="regular file.*order_app.py"):
        check_release.read_sdist_examples(sdist)


def test_duplicate_example_member_is_rejected(tmp_path):
    sdist = tmp_path / "fracture_recovery-0.1.0.tar.gz"
    write_sdist(sdist, duplicate="__init__.py")
    with pytest.raises(ValueError, match="exactly one.*__init__.py"):
        check_release.read_sdist_examples(sdist)
