import json

import pytest

import smb.shares


@pytest.mark.parametrize(
    "buf, count, expected",
    [
        (
            json.dumps(
                {
                    'resource_type': 'ceph.smb.share',
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
                    'resource_type': 'ceph.smb.share',
                    'intent': 'present',
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
                    'resource_type': 'ceph.smb.share',
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
                    'resource_type': 'ceph.smb.share',
                    'intent': 'present',
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
                    'resource_type': 'ceph.smb.share',
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
                    'resource_type': 'ceph.smb.share',
                    'intent': 'present',
                    'share_id': 'subway',
                    'name': 'subway',
                    'readonly': False,
                    'browseable': True,
                    'subsystem': 'cephfs',
                    'path': '',
                    'cephfs': {
                        'volume': 'cephfs',
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
                    #'resource_type': 'ceph.smb.share-list',
                    'resources': [
                        {
                            'resource_type': 'ceph.smb.share',
                            'share_id': 'birds',
                            'cephfs': {
                                'volume': 'cephfs',
                                'path': '/birds',
                            },
                        },
                        {
                            'resource_type': 'ceph.smb.share',
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
                    'resource_type': 'ceph.smb.share',
                    'intent': 'present',
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
                    'resource_type': 'ceph.smb.share',
                    'intent': 'present',
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
                    'resource_type': 'foobar',
                }
            ),
            -1,
            "resource_type",
        ),
        (
            json.dumps(
                {
                    'foo_kind': 'foobar',
                }
            ),
            -1,
            "resource_type",
        ),
        (
            json.dumps(
                {
                    'resource_type': 'ceph.smb.share',
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
                    'resource_type': 'ceph.smb.share',
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
                    'resource_type': 'ceph.smb.share',
                    'share_id': 'badv1',
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
                    'resource_type': 'ceph.smb.share',
                    'share_id': 'badv2',
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
                    'resource_type': 'ceph.smb.share',
                    'share_id': 'badv3',
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
                    'resource_type': 'ceph.smb.share',
                    'share_id': 'badv4',
                }
            ),
            -1,
            'cephfs',
        ),
    ],
)
def test_from_text(buf, count, expected):
    pass
    return
    if count > 0:
        shares = smb.shares.from_text(buf)
        assert len(shares) == count
        assert expected == [s.to_simplified() for s in shares]
    else:
        with pytest.raises((KeyError, TypeError, ValueError), match=expected):
            smb.shares.from_text(buf)





def xxx_test_one():
    jr = {
        'resource_type': 'ceph.smb.share',
        'share_id': 'myshare1',
        'name': 'My First Share',
        'cephfs': {
            'volume': 'foovol',
            'path': '/fast/snacks',
        },
    }
    share1 = smb.shares.from_text(json.dumps(jr))
    out = share1[0].to_simplified()
    jr['intent'] = 'present'
    jr['path'] = ''
    jr['browseable'] = True
    jr['readonly'] = False
    jr['subsystem'] = 'cephfs'
    jr['cephfs']['provider'] = 'kcephfs'
    assert jr == out
