from typing import Optional, List, Dict

import pytest

import smb.resourcelib
import smb.resources


@pytest.mark.parametrize(
    "params",
    [
        # minimal share (removed)
        {
            'data': {
                'resource_type': 'ceph.smb.share',
                'cluster_id': 'fakecluster1',
                'share_id': 'myshare1',
                'intent': 'removed',
            },
            'expected': [
                {
                    'resource_type': 'ceph.smb.share',
                    'cluster_id': 'fakecluster1',
                    'share_id': 'myshare1',
                    'intent': 'removed',
                }
            ],
        },
        # present share
        {
            'data': {
                'resource_type': 'ceph.smb.share',
                'cluster_id': 'fakecluster2',
                'share_id': 'myshare1',
                'intent': 'present',
                'browseable': False,
                'cephfs': {
                    'volume': 'cephfs',
                }

            },
            'expected': [
                {
                    'resource_type': 'ceph.smb.share',
                    'cluster_id': 'fakecluster2',
                    'share_id': 'myshare1',
                    'intent': 'present',
                    'name': 'myshare1',
                    'browseable': False,
                    'readonly': False,
                    'cephfs': {
                        'volume': 'cephfs',
                        'path': '/',
                        'provider': 'samba-vfs',
                    },
                }
            ],
        },
        # removed cluster
        {
            'data': {
                'resource_type': 'ceph.smb.cluster',
                'cluster_id': 'nocluster',
                'intent': 'removed',
            },
            'expected': [
                {
                    'resource_type': 'ceph.smb.cluster',
                    'cluster_id': 'nocluster',
                    'intent': 'removed',
                }
            ],
        },
        # cluster
        {
            'data': {
                'resource_type': 'ceph.smb.cluster',
                'cluster_id': 'nocluster',
                'auth_mode': 'active-directory',
                'domain_settings': {
                    'realm': 'FAKE.DOMAIN.TEST',
                    'join_sources': [
                        {'source_type': 'resource', 'ref': 'mydomauth1'},
                    ],
                },
            },
            'expected': [
                {
                    'resource_type': 'ceph.smb.cluster',
                    'cluster_id': 'nocluster',
                    'intent': 'present',
                    'auth_mode': 'active-directory',
                    'domain_settings': {
                        'realm': 'FAKE.DOMAIN.TEST',
                        'join_sources': [
                            {'source_type': 'resource', 'ref': 'mydomauth1'},
                        ],
                    },
                }
            ],
        },
    ],
)
def test_load_simplify_resources(params):
    data = params.get('data')
    loaded = smb.resourcelib.load(data)
    # test round tripping because asserting equality on the
    # objects is not simple
    sdata = [obj.to_simplified() for obj in loaded]
    assert params['expected'] == sdata
