import json

import pytest

import smb.cluster


@pytest.mark.parametrize(
    "obj, count, expected",
    [
        (
            {
                'object_type': 'ceph-smb-cluster',
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
                'object_type': 'ceph-smb-cluster',
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
                'object_type': 'ceph-smb-cluster-list',
                'values': [
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
            "object_type"
        ),
        (
            {"object_type": "junk"},
            -1,
            "object_type"
        ),
    ],
)
def test_from_request_objects(obj, count, expected):
    if count > 0:
        r1 = smb.cluster.ClusterRequest.from_dict(obj)
        clusters = r1.values
        assert len(clusters) == count
        assert [c.to_simplified() for c in clusters] == expected

        serialized = json.dumps(obj)
        r2 = smb.cluster.ClusterRequest.from_text(serialized)
        assert r2.values == clusters
    else:
        with pytest.raises(ValueError, match=expected):
            smb.cluster.ClusterRequest.from_dict(obj)
