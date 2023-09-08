import pytest

import smb.module
import smb.shares


@pytest.fixture
def mmod():
    store = smb.config_store.FakeConfigStore()
    cl = smb.cluster.FakeSMBCluster(
        'fake', private_store=store, public_store=store
    )
    sm = smb.shares.FakeSMBShareManager(
        cl, private_store=store, public_store=store
    )
    sm._shares = [
        smb.shares.SMBShare(
            'alice',
            "Alices Restaurant",
            '/alice',
            subsystem=smb.shares.SubSystem.CEPHFS,
            cephfs=smb.shares.CephFSStorage(
                volume='vol1',
                subvolumegroup='',
                subvolume='alice',
                path='/',
                provider=smb.shares.CephFSStorageProvider.KERNEL_MOUNT,
            ),
        ),
        smb.shares.SMBShare(
            'bob',
            "Bobs Burgers",
            '/bob',
            subsystem=smb.shares.SubSystem.CEPHFS,
            cephfs=smb.shares.CephFSStorage(
                volume='vol1',
                subvolumegroup='',
                subvolume='bob',
                path='/',
                provider=smb.shares.CephFSStorageProvider.KERNEL_MOUNT,
            ),
        ),
    ]
    sm._save()

    return smb.module.Module(
        'smb', '', '', public_store=store, private_store=store
    )


def test_cluster_ls(mmod):
    clusters = mmod.cluster_ls()
    assert len(clusters) == 2
    assert 'foo' in clusters
    assert 'bar' in clusters


def test_share_ls(mmod):
    shares = mmod.share_ls('fake')
    assert shares == [
        {'share_id': 'alice', 'name': 'Alices Restaurant', 'path': '/alice'},
        {'share_id': 'bob', 'name': "Bobs Burgers", 'path': '/bob'},
    ]


def test_cmd_share_ls(mmod):
    res, body, status = mmod.share_ls.command('fake', format='yaml')
    assert res == 0
    assert 'name: Alices R' in body
    assert 'name: Bobs B' in body
    assert not status


def test_cmd_share_rm(mmod):
    result = mmod.share_rm('fake', 'bob')
    assert isinstance(result, smb.shares.SMBShareStatus)
    assert result.state == 'removed'

    result = mmod.share_rm('fake', 'curly')
    assert isinstance(result, smb.shares.SMBShareStatus)
    assert result.state == 'not present'


def test_cmd_share_create(mmod):
    result = mmod.share_create(
        cluster_id='fake',
        share_id='simple',
        path='/',
        cephfs_volume='cephfs',
    )
    assert isinstance(result, smb.shares.SMBShareStatus)
    assert result.state == 'created'


def test_cmd_share_apply(mmod):
    import json

    mmod = smb.module.Module('smb', '', '')
    result = mmod.share_apply(
        cluster_id='fake',
        inbuf=json.dumps(
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
    )
    assert isinstance(result, smb.shares.ApplyResults)
    simpleres = result.to_simplified()
    assert len(simpleres) == 2
    assert simpleres[0] == {
        'share_id': 'birds',
        'name': 'birds',
        'path': '',
        'status': {'state': 'created'},
    }
    assert simpleres[1] == {
        'share_id': 'reptiles',
        'name': 'reptiles',
        'path': '',
        'status': {'state': 'created'},
    }


def test_share_dump_config(mmod):
    cfg = mmod.share_dump_config('fake')
    assert cfg == {
        'samba-container-config': "v0",
        'configs': {
            'fake': {
                'instance_name': 'FAKE',
                'instance_features': [],
                'shares': ['Alices Restaurant', 'Bobs Burgers'],
                'globals': ['default', 'fake'],
            },
        },
        'shares': {
            'Alices Restaurant': {
                'options': {
                    'path': '/alice',
                    'read only': 'No',
                    'browseable': 'Yes',
                    'cephmeta:id': 'alice',
                    'cephmeta:name': 'Alices Restaurant',
                },
            },
            'Bobs Burgers': {
                'options': {
                    'path': '/bob',
                    'read only': 'No',
                    'browseable': 'Yes',
                    'cephmeta:id': 'bob',
                    'cephmeta:name': 'Bobs Burgers',
                },
            },
        },
        'globals': {
            'default': {
                'server min protocol': 'SMB2',
                'load printers': 'No',
                'printing': 'bsd',
                'printcap name': '/dev/null',
                'disable spoolss': 'Yes',
            },
            'fake': {},
        },
    }
