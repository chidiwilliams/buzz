import pytest

from buzz.paths import safe_filename_component


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
