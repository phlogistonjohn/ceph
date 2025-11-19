import pytest

import cephutil
import smbutil


@pytest.mark.default
def test_arbitrary_listdir(smb_cfg, share_name):
    with smbutil.connection(smb_cfg, share_name) as sharep:
        contents = sharep.listdir()
        assert isinstance(contents, list)


@pytest.mark.default
def test_create_dir(smb_cfg, share_name):
    with smbutil.connection(smb_cfg, share_name) as sharep:
        tdir = sharep / 'test_create_dir'
        tdir.mkdir(exist_ok=True)
        try:
            contents = sharep.listdir()
            assert 'test_create_dir' in contents
        finally:
            tdir.rmdir()


@pytest.mark.default
def test_create_file(smb_cfg, share_name):
    with smbutil.connection(smb_cfg, share_name) as sharep:
        fname = sharep / 'file1.dat'
        fname.write_text('HELLO WORLD\n')
        try:
            contents = sharep.listdir()
            assert 'file1.dat' in contents

            txt = fname.read_text()
            assert txt == 'HELLO WORLD\n'
        finally:
            fname.unlink()


@pytest.mark.default
def test_poke_mgr_module(smb_cfg):
    jr = cephutil.cephadm_shell_cmd(
        smb_cfg,
        ['ceph', 'smb', 'show'],
        load_json=True,
    )
    assert jr
    clusters = [
        r
        for r in jr.obj['resources']
        if r['resource_type'] == 'ceph.smb.cluster'
    ]
    assert len(clusters) == 1


@pytest.mark.default
def test_poke_mgr_module2(smb_cfg):
    jr = cephutil.cephadm_shell_cmd(
        smb_cfg,
        ['ceph', 'smb', 'show', 'ceph.smb.share'],
        load_json=True,
    )
    assert jr.obj
    assert len(jr.obj['resources']) == 2
    shares = [
        r
        for r in jr.obj['resources']
        if r['resource_type'] == 'ceph.smb.share'
    ]
    assert len(shares) == 2

    share = shares[0]
    share['cluster_id'] = 'jimbo'
    jr = cephutil.cephadm_shell_cmd(
        smb_cfg,
        ['ceph', 'smb', 'apply', '-i-'],
        load_json=cephutil.LoadJSON.BOTH,
        input_json={'resources': [share]},
    )
    assert jr.returncode != 0
    assert jr.obj
    assert not jr.obj.get('success')
