import json

import pytest

import smb.cluster


@pytest.mark.parametrize(
    "obj, count, expected",
    [
        (
            {
                'resource_type': 'ceph.smb.cluster',
                'cluster_id': 'smb1',
                'intent': 'present',
                'auth_mode': 'user',
                'user_group_settings': {
                    'user_group_sources': [
                        {
                            'source_type': 'inline',
                            'users': [
                                {
                                    'name': "charlie",
                                    'password': 'G01d3nT1ck37',
                                },
                            ],
                        }
                    ],
                },
            },
            1,
            [
                {
                    'cluster_id': 'smb1',
                    'intent': 'present',
                    'auth_mode': 'user',
                    'user_group_settings': {
                        'user_group_sources': [
                            {
                                'source_type': 'inline',
                                'users': [
                                    {
                                        'name': "charlie",
                                        'password': 'G01d3nT1ck37',
                                    },
                                ],
                            }
                        ],
                    },
                },
            ],
        ),
        (
            {
                'resource_type': 'ceph.smb.cluster',
                'cluster_id': 'smb1',
                'intent': 'present',
                'auth_mode': 'active-directory',
                'domain_settings': {
                    'realm': 'FLUBBER.DOMAIN.TEST',
                    'join_sources': [
                        {
                            'source_type': 'password',
                            'username': "Administrator",
                            'password': 'v3r^S3cur3',
                        },
                    ],
                },
            },
            1,
            [
                {
                    'cluster_id': 'smb1',
                    'intent': 'present',
                    'auth_mode': 'active-directory',
                    'domain_settings': {
                        'realm': 'FLUBBER.DOMAIN.TEST',
                        'join_sources': [
                            {
                                'source_type': 'password',
                                'username': "Administrator",
                                'password': 'v3r^S3cur3',
                            },
                        ],
                    },
                },
            ],
        ),
        (
            {
                'resources': [
                    {
                        'cluster_id': 'smb1',
                        'intent': 'present',
                        'auth_mode': 'user',
                        'user_group_settings': {
                            'user_group_sources': [
                                {
                                    'source_type': 'inline',
                                    'users': [
                                        {
                                            'name': "charlie",
                                            'password': 'G01d3nT1ck37',
                                        },
                                    ],
                                }
                            ],
                        },
                    },
                    {
                        'cluster_id': 'smb2',
                        'intent': 'present',
                        'auth_mode': 'active-directory',
                        'domain_settings': {
                            'realm': 'FLUBBER.DOMAIN.TEST',
                            'join_sources': [
                                {
                                    'source_type': 'password',
                                    'username': "Administrator",
                                    'password': 'v3r^S3cur3',
                                },
                            ],
                        },
                    },
                ],
            },
            2,
            [
                {
                    'cluster_id': 'smb1',
                    'intent': 'present',
                    'auth_mode': 'user',
                    'user_group_settings': {
                        'user_group_sources': [
                            {
                                'source_type': 'inline',
                                'users': [
                                    {
                                        'name': "charlie",
                                        'password': 'G01d3nT1ck37',
                                    },
                                ],
                            }
                        ],
                    },
                },
                {
                    'cluster_id': 'smb2',
                    'intent': 'present',
                    'auth_mode': 'active-directory',
                    'domain_settings': {
                        'realm': 'FLUBBER.DOMAIN.TEST',
                        'join_sources': [
                            {
                                'source_type': 'password',
                                'username': "Administrator",
                                'password': 'v3r^S3cur3',
                            },
                        ],
                    },
                },
            ],
        ),
        (
            {},
            -1,
            "resource_type"
        ),
        (
            {"resource_type": "junk"},
            -1,
            "resource_type"
        ),
    ],
)
def test_from_request_objects(obj, count, expected):
    import smb.resource

    if count > 0:
        #r1 = smb.cluster.ClusterRequest.from_dict(obj)
        #clusters = r1.values
        #assert len(clusters) == count
        #assert expected == [c.to_simplified() for c in clusters]

        #serialized = json.dumps(obj)
        #r2 = smb.cluster.ClusterRequest.from_text(serialized)
        #assert r2.values == clusters
        clusters = smb.resource.load(obj)
        assert len(clusters) == count
        assert expected == [c.to_simplified() for c in clusters]
    else:
        with pytest.raises(ValueError, match=expected):
            smb.cluster.ClusterRequest.from_dict(obj)



def test_foo():
    from smb.resource import Example, Bonk

    e1 = Example('finle', '99-a')
    s1 = e1.to_simplified()
    print(s1)
    Example.from_simplified(s1)
    e1.contents = [
        Bonk(label='jo', width=43, height=8, length=12),
        Bonk(label='moo', width=3, height=18, length=112),
        Bonk(label='go', width=2, height=99, length=102),
    ]
    s1 = e1.to_simplified()
    print(s1)
    x = Example.from_simplified(s1)
    assert x.name == 'finle'
    assert x.serial_num == '99-a'
    assert len(x.contents) == 3
    assert x.contents[0].label == 'jo'
    assert x.contents[0].width == 43
    assert x.contents[1].label == 'moo'
    assert x.contents[1].width == 3
