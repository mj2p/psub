import os

import pytest
import yaml


@pytest.fixture(name="test_config_file_path")
def return_test_config_file_path(tmp_path):
    return os.path.join(tmp_path, "config.yaml")


@pytest.fixture(name="config_file")
def create_test_config_file(test_config_file_path, config):
    yaml.dump(config, open(test_config_file_path, "w+"))


@pytest.fixture(name="config")
def create_test_config():
    return {
        "server": {
            "host": "demo.subsonic.org",
            "username": "test_user",
            "password": "test_password",
            "ssl": False,
            "api": "1.16.0",
            "verify_ssl": True,
        },
        "streaming": {
            "format": "raw",
            "invert_random": False,
            "notify": True,
            "player": "test",
            "controls": {"previous": "1", "next": "2", "restart": "3", "exit": "4"},
            "ffplay": {"display": False, "show_mode": 0, "pre_exe": ""},
            "vlc": {"playing_interval": 2},
            "mpv": {},
        },
    }
