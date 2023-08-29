import json

import pytest

import smb.shares


@pytest.mark.parametrize(
    "buf, count, expected",
    [
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share',
                    'share_id': 'snackage',
                    'name': 'Snack Tray',
                    'cephfs': {
                        'volume': 'foovol',
                        'path': '/fast/snacks',
                    },
                }
            ),
            1,
            [
                {
                    'share_id': 'snackage',
                    'name': 'Snack Tray',
                    'readonly': False,
                    'browseable': True,
                    'subsystem': 'cephfs',
                    'path': '',
                    'cephfs': {
                        'volume': 'foovol',
                        'path': '/fast/snacks',
                        'provider': 'kcephfs',
                    },
                },
            ],
        ),
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share',
                    'share_id': 'transport',
                    'cephfs': {
                        'volume': 'cephfs',
                        'subvolume': 'car/boat',
                        'path': '/',
                    },
                }
            ),
            1,
            [
                {
                    'share_id': 'transport',
                    'name': 'transport',
                    'readonly': False,
                    'browseable': True,
                    'subsystem': 'cephfs',
                    'path': '',
                    'cephfs': {
                        'volume': 'cephfs',
                        'subvolumegroup': 'car',
                        'subvolume': 'boat',
                        'path': '/',
                        'provider': 'kcephfs',
                    },
                },
            ],
        ),
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share',
                    'share_id': 'subway',
                    'cephfs': {
                        'volume': 'cephfs',
                        'subvolume': 'way',
                        'path': '/',
                    },
                }
            ),
            1,
            [
                {
                    'share_id': 'subway',
                    'name': 'subway',
                    'readonly': False,
                    'browseable': True,
                    'subsystem': 'cephfs',
                    'path': '',
                    'cephfs': {
                        'volume': 'cephfs',
                        'subvolumegroup': '',
                        'subvolume': 'way',
                        'path': '/',
                        'provider': 'kcephfs',
                    },
                },
            ],
        ),
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share-list',
                    'values': [
                        {
                            'share_id': 'birds',
                            'cephfs': {
                                'volume': 'cephfs',
                                'path': '/birds',
                            },
                        },
                        {
                            'share_id': 'reptiles',
                            'cephfs': {
                                'volume': 'cephfs',
                                'path': '/reptiles',
                            },
                        },
                    ],
                }
            ),
            2,
            [
                {
                    'share_id': 'birds',
                    'name': 'birds',
                    'readonly': False,
                    'browseable': True,
                    'subsystem': 'cephfs',
                    'path': '',
                    'cephfs': {
                        'volume': 'cephfs',
                        'path': '/birds',
                        'provider': 'kcephfs',
                    },
                },
                {
                    'share_id': 'reptiles',
                    'name': 'reptiles',
                    'readonly': False,
                    'browseable': True,
                    'subsystem': 'cephfs',
                    'path': '',
                    'cephfs': {
                        'volume': 'cephfs',
                        'path': '/reptiles',
                        'provider': 'kcephfs',
                    },
                },
            ],
        ),
        (
            json.dumps(
                {
                    'object_type': 'foobar',
                }
            ),
            -1,
            "object_type",
        ),
        (
            json.dumps(
                {
                    'foo_kind': 'foobar',
                }
            ),
            -1,
            "object_type",
        ),
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share',
                    'name': 'Bad Mojo',
                    'cephfs': {
                        'volume': 'foovol',
                        'path': '/fast/snacks',
                    },
                }
            ),
            -1,
            'share_id',
        ),
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share',
                    'share_id': '',
                    'name': 'Bad Mojo',
                    'cephfs': {
                        'volume': 'foovol',
                        'path': '/fast/snacks',
                    },
                }
            ),
            -1,
            'share_id',
        ),
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share',
                    'share_id': 'badv',
                    'cephfs': {
                        'path': '/fast/snacks',
                    },
                }
            ),
            -1,
            'volume',
        ),
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share',
                    'share_id': 'badv',
                    'cephfs': {
                        'volume': '',
                        'path': '/fast/snacks',
                    },
                }
            ),
            -1,
            'volume',
        ),
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share',
                    'share_id': 'badv',
                    'cephfs': {
                        'volume': 'fooish',
                        'subvolume': 'my/bad/input',
                        'path': '/fast/snacks',
                    },
                }
            ),
            -1,
            'subvolume',
        ),
        (
            json.dumps(
                {
                    'object_type': 'ceph-smb-share',
                    'share_id': 'badv',
                }
            ),
            -1,
            'cephfs',
        ),
    ],
)
def test_from_text(buf, count, expected):
    if count > 0:
        shares = smb.shares.from_text(buf)
        assert len(shares) == count
        assert [s.share.to_simplified() for s in shares] == expected
    else:
        with pytest.raises(ValueError, match=expected):
            smb.shares.from_text(buf)
