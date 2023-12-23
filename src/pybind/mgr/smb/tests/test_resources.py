from typing import Optional, List, Dict

import pytest

import smb.resourcelib
import smb.resources
from smb import enums


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


YAML1 = """
resource_type: ceph.smb.cluster
cluster_id: chacha
auth_mode: active-directory
domain_settings:
  realm: CEPH.SINK.TEST
  join_sources:
    - source_type: resource
      ref: bob
    - source_type: password
      username: Administrator
      password: fallb4kP4ssw0rd
---
resource_type: ceph.smb.share
cluster_id: chacha
share_id: s1
cephfs:
  volume: cephfs
  path: /
---
resource_type: ceph.smb.share
cluster_id: chacha
share_id: s2
name: My Second Share
cephfs:
  volume: cephfs
  subvolume: cool/beans
---
resource_type: ceph.smb.share
cluster_id: chacha
share_id: s0
intent: removed
# deleted this test share
---
resource_type: ceph.smb.join.auth
auth_id: bob
values:
  username: BobTheAdmin
  password: someJunkyPassw0rd
---
resource_type: ceph.smb.join.auth
auth_id: alice
intent: removed
# alice left the company
"""


def test_load_yaml_resource():
    import yaml

    loaded = smb.resourcelib.load(yaml.safe_load_all(YAML1))
    assert len(loaded) == 6

    assert isinstance(loaded[0], smb.resources.Cluster)
    cluster = loaded[0]
    assert cluster.cluster_id == 'chacha'
    assert cluster.intent == enums.Intent.PRESENT
    assert cluster.settings.auth_mode == enums.AuthMode.ACTIVE_DIRECTORY
    assert cluster.settings.domain_settings.realm == 'CEPH.SINK.TEST'
    assert len(cluster.settings.domain_settings.join_sources) == 2
    jsrc = cluster.settings.domain_settings.join_sources
    assert jsrc[0].source_type == enums.JoinSourceType.RESOURCE
    assert jsrc[0].ref == 'bob'
    assert jsrc[1].source_type == enums.JoinSourceType.PASSWORD
    assert jsrc[1].username == 'Administrator'
    assert jsrc[1].password == 'fallb4kP4ssw0rd'

    assert isinstance(loaded[1], smb.resources.Share)
    assert isinstance(loaded[2], smb.resources.Share)
    assert isinstance(loaded[3], smb.resources.Share)
    assert isinstance(loaded[4], smb.resources.JoinAuth)
    assert isinstance(loaded[5], smb.resources.JoinAuth)
