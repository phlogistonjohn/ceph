import pytest
import errno
import uuid
from unittest import mock

from ceph.fs import earmarking
from ceph.fs.earmarking import (
    CephFSVolumeEarmarking,
    EarmarkException,
    EarmarkParseError,
    EarmarkTopScope,
    parse_earmark,
)

XATTR_SUBVOLUME_EARMARK_NAME = 'user.ceph.subvolume.earmark'


class TestCephFSVolumeEarmarking:

    @pytest.fixture
    def mock_fs(self):
        return mock.Mock()

    @pytest.fixture
    def earmarking(self, mock_fs):
        return CephFSVolumeEarmarking(mock_fs, "/test/path")

    def test_parse_earmark_valid(self):
        earmark_value = "nfs.subsection1.subsection2"
        result = parse_earmark(earmark_value)
        assert result.top == EarmarkTopScope.NFS
        assert result.subsections == ["subsection1", "subsection2"]

    def test_parse_earmark_empty_string(self):
        result = parse_earmark("")
        assert result is None

    def test_parse_earmark_invalid_scope(self):
        with pytest.raises(EarmarkParseError):
            parse_earmark("invalid.scope")

    def test_parse_earmark_empty_sections(self):
        with pytest.raises(EarmarkParseError):
            parse_earmark("nfs..section")

    def test_validate_earmark_valid_empty(self, earmarking):
        assert earmarking._validate_earmark("")

    def test_validate_earmark_valid_smb(self, earmarking):
        assert earmarking._validate_earmark("smb.cluster.cluster_id")

    def test_validate_earmark_invalid_smb_format(self, earmarking):
        assert not earmarking._validate_earmark("smb.invalid.format")

    def test_get_earmark_success(self, earmarking):
        earmarking.fs.getxattr.return_value = b'nfs.valid.earmark'
        result = earmarking.get_earmark()
        assert result == 'nfs.valid.earmark'

    def test_get_earmark_handle_error(self, earmarking):
        earmarking.fs.getxattr.side_effect = OSError(errno.EIO, "I/O error")
        with pytest.raises(EarmarkException) as excinfo:
            earmarking.get_earmark()
        assert excinfo.value.errno == -errno.EIO

    def test_set_earmark_valid(self, earmarking):
        earmark = "nfs.valid.earmark"
        earmarking.set_earmark(earmark)
        earmarking.fs.setxattr.assert_called_with(
            "/test/path", XATTR_SUBVOLUME_EARMARK_NAME, earmark.encode('utf-8'), 0
        )

    def test_set_earmark_invalid(self, earmarking):
        with pytest.raises(EarmarkException) as excinfo:
            earmarking.set_earmark("invalid.earmark")
        assert excinfo.value.errno == errno.EINVAL

    def test_set_earmark_handle_error(self, earmarking):
        earmarking.fs.setxattr.side_effect = OSError(errno.EIO, "I/O error")
        with pytest.raises(EarmarkException) as excinfo:
            earmarking.set_earmark("nfs.valid.earmark")
        assert excinfo.value.errno == -errno.EIO

    def test_clear_earmark(self, earmarking):
        with mock.patch.object(earmarking, 'set_earmark') as mock_set_earmark:
            earmarking.clear_earmark()
            mock_set_earmark.assert_called_once_with("")


@pytest.mark.parametrize(('e', 'err'), [
    ('mixed.v0a0.nfs_smb.NEW', None),
    ('mixed.v0a0.nfs_smb.ANY', None),
    ('mixed.v0a0.nfs_smb.ERERESIiMzNERFVVZneImQ', None),
    ('mixed.v0a0.nfs.ERERESIiMzNERFVVZneImQ', None),
    ('mixed.v0a0.smb.ERERESIiMzNERFVVZneImQ', None),
    ('mixed.v0a2.nfs_smb.ERERESIiMzNERFVVZneImQ', None),
    ('mixed', 'missing version'),
    ('mixed.bob.y.y', 'invalid version'),
    ('mixed.v0a0', 'missing subsection'),
    ('mixed.v0a0.asdf', 'missing subsection'),
    ('mixed.v0a0.asdf.money', 'not a valid Proto'),
    ('mixed.v0a0.nfs.money', 'invalid ussid'),
    ('mixed.v999a999.nfs_smb.ANY', 'unknown version'),
])
def test_parse_mixed_proto_earmark(e, err):
    known_versions = [
        earmarking.EarmarkVersion(0, 'a', 0),
        earmarking.EarmarkVersion(0, 'a', 1),
        earmarking.EarmarkVersion(0, 'a', 2),
    ]
    try:
        orig = earmarking._known_versions
        earmarking._known_versions = known_versions
        if err:
            with pytest.raises(Exception, match=err):
                parse_earmark(e)
        else:
            mpe = parse_earmark(e)
            assert str(mpe) == e, "stringify round trip failed"
    finally:
        earmarking._known_versions = orig


def test_parse_mixed_proto_earmark_wrong_top():
    with pytest.raises(earmarking.EarmarkParseError, match='top'):
        earmarking.MixedProtoEarmark.parse(
            'smb.cluster.foo'
        )


@pytest.mark.parametrize(
    ('params', 'conv'),
    [
        (
            ([uuid.UUID('b239139a-e19c-46bb-80b9-e19b24d8e2f3')], {}),
            'mixed.v0b99.nfs_smb.sjkTmuGcRruAueGbJNji8w',
        ),
        (
            ([earmarking.PseduoUSSID.ANY], {}),
            'mixed.v0b99.nfs_smb.ANY',
        ),
        (
            ([earmarking.PseduoUSSID.NEW], {}),
            'mixed.v0b99.nfs_smb.NEW',
        ),
        (
            (
                [uuid.UUID('b239139a-e19c-46bb-80b9-e19b24d8e2f3')],
                {'protos': (earmarking.Proto.SMB,)},
            ),
            'mixed.v0b99.smb.sjkTmuGcRruAueGbJNji8w',
        ),
        (
            (
                [uuid.UUID('b239139a-e19c-46bb-80b9-e19b24d8e2f3')],
                {'protos': (earmarking.Proto.NFS,)},
            ),
            'mixed.v0b99.nfs.sjkTmuGcRruAueGbJNji8w',
        ),
    ],
)
def test_build_mixed_proto_earmark_vals(params, conv):
    args, kwargs = params
    known_versions = [
        earmarking.EarmarkVersion(0, 'a', 0),
        earmarking.EarmarkVersion(0, 'a', 1),
        earmarking.EarmarkVersion(0, 'a', 2),
        earmarking.EarmarkVersion(0, 'b', 99),
    ]
    try:
        orig = earmarking._known_versions
        earmarking._known_versions = known_versions
        assert (
            str(earmarking.MixedProtoEarmark.from_ussid(*args, **kwargs))
            == conv
        )
    finally:
        earmarking._known_versions = orig
