import os
from unittest.mock import patch

import pytest

from buzz.paths import resolve_document_portal_path, safe_filename_component


@pytest.mark.parametrize(
    "name,expected",
    [
        ("中文 | QVD-123.", "中文 _ QVD-123#"),
        ("foo:bar?.wav", "foo_bar_.wav"),
        ("trailing-dot.", "trailing-dot#"),
        ("trailing-space ", "trailing-space#"),
        ("emoji-🚀", "emoji-🚀"),
        ("CON", "_CON"),
    ],
)
def test_safe_filename_component(name, expected):
    assert safe_filename_component(name) == expected


class TestResolveDocumentPortalPath:
    @staticmethod
    def portal_path(name="audio.mp3"):
        return f"/run/user/{os.getuid()}/doc/abc123/{name}"

    def test_returns_regular_path_unchanged(self):
        assert resolve_document_portal_path("/home/user/a.mp3") == "/home/user/a.mp3"
        assert resolve_document_portal_path("") == ""

    def test_resolves_existing_file_to_host_path(self, tmp_path):
        host_file = tmp_path / "audio.mp3"
        host_file.write_bytes(b"")
        xattrs = {self.portal_path(): os.fsencode(str(host_file))}

        with patch("buzz.paths.sys.platform", "linux"), patch(
            "buzz.paths.os.getxattr", side_effect=lambda p, _: xattrs[p]
        ):
            assert resolve_document_portal_path(self.portal_path()) == str(host_file)

    def test_resolves_new_save_file_via_document_folder(self, tmp_path):
        portal_file = self.portal_path("out.txt")
        xattrs = {os.path.dirname(portal_file): os.fsencode(str(tmp_path))}

        def getxattr(path, _name):
            if path not in xattrs:
                raise OSError("no xattr")
            return xattrs[path]

        with patch("buzz.paths.sys.platform", "linux"), patch(
            "buzz.paths.os.getxattr", side_effect=getxattr
        ):
            assert resolve_document_portal_path(portal_file) == str(
                tmp_path / "out.txt"
            )

    def test_keeps_portal_path_when_host_path_is_not_reachable(self, tmp_path):
        missing = tmp_path / "missing-dir" / "audio.mp3"
        with patch("buzz.paths.sys.platform", "linux"), patch(
            "buzz.paths.os.getxattr", return_value=os.fsencode(str(missing))
        ):
            assert resolve_document_portal_path(self.portal_path()) == self.portal_path()

    def test_keeps_portal_path_when_xattr_is_unavailable(self):
        with patch("buzz.paths.sys.platform", "linux"), patch(
            "buzz.paths.os.getxattr", side_effect=OSError("unsupported")
        ):
            assert resolve_document_portal_path(self.portal_path()) == self.portal_path()
