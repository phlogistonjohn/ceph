import pytest


@pytest.mark.default
def test_hello():
    print("Hello, tests")


@pytest.mark.foobar
def test_goodbye():
    import time

    time.sleep(60 * 60)


@pytest.mark.default
def test_smb1(smb_cfg):
    assert smb_cfg._data
