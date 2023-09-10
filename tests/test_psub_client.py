import hashlib
import os
import random
import threading
import time
from queue import LifoQueue
from random import SystemRandom
from typing import Dict
from unittest.mock import call
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import yaml
from packaging import version

from client.notifications import Notifications
from client.psub import PsubClient, click
from players.base_player import PsubPlayer
from players.ffplay import Ffplay
from players.mpv import Mpv
from players.vlc import Vlc


@pytest.mark.parametrize("notify", (False, True))
@pytest.mark.parametrize("has_config", (False, True))
def test_init(mocker, test_config_file_path, config, has_config, notify):
    """
    Test the __init__ method, ensuring all class attributes are set correctly
    We test with and without an existing config file
    """
    # set up mocks
    edit_mock = mocker.patch.object(click, "edit")
    set_default_config_mock = mocker.patch.object(PsubClient, "set_default_config")
    set_player_mock = mocker.patch.object(PsubClient, "set_player")

    def create_config(*args, **kwargs):  # noqa
        """
        Helper method to create the temp config file
        """
        config["streaming"]["notify"] = notify
        yaml.dump(config, open(test_config_file_path, "w+"))
        return None

    if has_config:
        # testing with a config, file needs to exist before creating the PsubClient object
        create_config()
    else:
        # testing without a config, create the config file when the 'set_default_config' mock is called
        set_default_config_mock.side_effect = create_config

    # call the __init__ method
    psub_client = PsubClient(test_config_file_path)

    if has_config:
        # config existed already so we shouldn't call these methods
        assert set_default_config_mock.call_count == 0
        assert edit_mock.call_count == 0
    else:
        # without a pre-existing config file we should call these
        set_default_config_mock.assert_called_once_with(test_config_file_path)
        edit_mock.assert_called_once_with(filename=test_config_file_path)

    # test the 'server' config
    assert psub_client.host == config["server"]["host"]
    assert psub_client.username == config["server"]["username"]
    assert psub_client.password == config["server"]["password"]
    assert psub_client.api == config["server"]["api"]
    assert psub_client.ssl == config["server"]["ssl"]
    assert psub_client.verify_ssl == config["server"]["verify_ssl"]
    # test the 'streaming' config
    assert psub_client.format == config["streaming"]["format"]
    assert psub_client.invert_random == config["streaming"]["invert_random"]
    assert psub_client.notify == config["streaming"]["notify"]
    assert set_player_mock.call_count == 1
    set_player_mock.assert_has_calls([call(config["streaming"]["player"], {})])
    # test the controls
    assert psub_client.previous == config["streaming"]["controls"]["previous"]
    assert psub_client.next == config["streaming"]["controls"]["next"]
    assert psub_client.restart == config["streaming"]["controls"]["restart"]
    assert psub_client.exit == config["streaming"]["controls"]["exit"]

    if psub_client.notify:
        # ensure notifications is set correctly
        assert isinstance(psub_client.notifications, Notifications)

    # make sure we have the necessary queue and list objects
    assert psub_client.search_results == []
    assert isinstance(psub_client.input_queue, LifoQueue)
    assert "add_input" in [t.name for t in threading.enumerate()]
    assert psub_client.track_index == 0
    assert psub_client.track_list == []

    # ensure the lock file is cleared
    assert not os.path.exists(os.path.join(click.get_app_dir("pSub"), "play.lock"))


def test_set_player_no_module_found(test_config_file_path, config_file, config):
    with pytest.raises(click.UsageError) as excinfo:
        PsubClient(test_config_file_path)

    assert f"Unable to load a player matching '{config['streaming']['player']}'" in str(
        excinfo.value
    )
    assert "Available options are:" in str(excinfo.value)
    assert "Please adjust your config file by running:" in str(excinfo.value)
    assert "  psub -c" in str(excinfo.value)


def test_set_player_ffplay(test_config_file_path, config):
    config["streaming"]["player"] = "ffplay"
    yaml.dump(config, open(test_config_file_path, "w+"))
    psub_client = PsubClient(test_config_file_path)

    assert isinstance(psub_client.player, Ffplay)


def test_set_player_mpv(test_config_file_path, config):
    config["streaming"]["player"] = "mpv"
    yaml.dump(config, open(test_config_file_path, "w+"))
    psub_client = PsubClient(test_config_file_path)

    assert isinstance(psub_client.player, Mpv)


def test_set_player_vlc(test_config_file_path, config):
    config["streaming"]["player"] = "vlc"
    yaml.dump(config, open(test_config_file_path, "w+"))
    psub_client = PsubClient(test_config_file_path)

    assert isinstance(psub_client.player, Vlc)


# @pytest.mark.parametrize(
#     'config_pre_exe,expected_pre_exe',
#     [
#         ('', []),
#         ('command_1', ['command_1']),
#         ('command_1 command_2', ['command_1', 'command_2']),
#         ('command_1 command_2|command_3', ['command_1', 'command_2|command_3'])
#     ]
# )
# def test_parse_pre_exe(test_config_file_path, config_file, config_pre_exe, expected_pre_exe):
#     """
#     Ensure that pre_exe parsing acts correctly
#     """
#     psub_client = pSub(test_config_file_path)
#     psub_client.pre_exe = config_pre_exe
#     psub_client.parse_pre_exe()
#     assert psub_client.pre_exe == expected_pre_exe


@pytest.mark.parametrize("successful", [True, False])
def test_test_config(mocker, test_config_file_path, config_file, config, successful):
    """
    test_config fires a ping request to the server to ensure the 'server' config is valid
    """
    # set up mocks
    secho_mock = mocker.patch.object(click, "secho")
    mocker.patch.object(PsubClient, "set_player")
    ping_url = "test_url/ping"
    create_url_mock = mocker.patch.object(
        PsubClient, "create_url", return_value=ping_url
    )
    make_request_mock = mocker.patch.object(
        PsubClient, "make_request", return_value=successful
    )

    psub_client = PsubClient(test_config_file_path)

    if successful:
        test_success = psub_client.test_config()
        assert test_success is None
    else:
        with pytest.raises(click.ClickException):
            psub_client.test_config()

    secho_mock.assert_has_calls(
        [
            call("Testing Server Connection", fg="green"),
            call(
                f"{'https' if config['server']['ssl'] else 'http'}://{config['server']['username']}@{config['server']['host']}",
                fg="blue",
            ),
        ]
    )
    create_url_mock.assert_called_once_with("ping")
    make_request_mock.assert_called_once_with(url=ping_url)


def test_hash_password(mocker, test_config_file_path, config_file):
    """
    The hash_password method creates a salt and salted token based on an md5 hash of the server password
    """
    # create mocks
    salt = "test_salt"
    token = "test_salted_token"
    choice_mock = mocker.patch.object(SystemRandom, "choice")
    choice_mock.side_effect = [
        char for char in salt
    ]  # return a single character each time the mock is called
    md5_mock = mocker.patch.object(hashlib, "md5")
    md5_mock.return_value.hexdigest.return_value = token
    mocker.patch.object(PsubClient, "set_player")

    psub_client = PsubClient(test_config_file_path)

    test_token, test_salt = psub_client.hash_password()

    assert test_token == token
    assert test_salt == salt

    md5_mock.assert_called_once()


@pytest.mark.parametrize("api_version", ["1.12.0", "1.13.0", "1.16.0"])
@pytest.mark.parametrize("ssl", [True, False])
def test_create_url(mocker, test_config_file_path, config, api_version, ssl):
    test_token = "test_token"
    test_salt = "test_salt"
    hash_password_mock = mocker.patch.object(
        PsubClient, "hash_password", return_value=(test_token, test_salt)
    )
    mocker.patch.object(PsubClient, "set_player")
    config["server"]["api"] = api_version
    config["server"]["ssl"] = ssl
    yaml.dump(config, open(test_config_file_path, "w+"))

    psub_client = PsubClient(test_config_file_path)

    test_endpoint = "test_endpoint"
    test_url = psub_client.create_url(test_endpoint)
    parsed_url = urlparse(test_url)
    params = parse_qs(parsed_url.query)

    expected_proto = "https" if ssl else "http"

    assert parsed_url.scheme == expected_proto
    assert parsed_url.netloc == config["server"]["host"]
    assert params["u"] == [config["server"]["username"]]
    assert params["v"] == [api_version]
    assert params["c"] == ["pSub"]
    assert params["f"] == ["json"]

    if version.parse(api_version) < version.parse("1.13.0"):
        assert list(params.keys()) == ["u", "p", "v", "c", "f"]
        assert hash_password_mock.call_count == 0
        assert parsed_url.path == f"/rest/{test_endpoint}.view"
        assert params["p"] == [config["server"]["password"]]
    else:
        assert list(params.keys()) == ["u", "t", "s", "v", "c", "f"]
        hash_password_mock.assert_called_once()
        assert parsed_url.path == f"/rest/{test_endpoint}"
        assert params["t"] == [test_token]
        assert params["s"] == [test_salt]


@pytest.mark.parametrize("response", ["success", "failed", "invalid_json", "exception"])
@pytest.mark.parametrize("status_code", [200, 404, 502])
@pytest.mark.parametrize("verify_ssl", [True, False])
def test_make_request(
    mocker,
    test_config_file_path,
    config,
    requests_mock,
    response,
    status_code,
    verify_ssl,
):
    mocker.patch.object(PsubClient, "set_player")

    if response in ["success", "failed"]:
        return_response = {"subsonic-response": {"status": response}}
    else:
        return_response = response

    test_url = "https://test-url.com"

    if response == "exception":
        requests_mock.get(test_url, exc=requests.exceptions.ConnectionError)
    elif response == "invalid_json":
        requests_mock.get(test_url, status_code=status_code, text=return_response)
    else:
        requests_mock.get(test_url, status_code=status_code, json=return_response)

    config["server"]["verify_ssl"] = verify_ssl
    yaml.dump(config, open(test_config_file_path, "w+"))

    psub_client = PsubClient(test_config_file_path)

    if status_code > 200 or response == "exception":
        with pytest.raises(click.UsageError):
            psub_client.make_request(test_url)
        return
    else:
        got_response = psub_client.make_request(test_url)

    if response in ["failed", "invalid_json"]:
        assert got_response is None
    else:
        assert got_response == return_response


@pytest.mark.parametrize("status_code", [200, 404, 502])
def test_make_request_content(
    mocker, test_config_file_path, config, config_file, requests_mock, status_code
):
    mocker.patch.object(PsubClient, "set_player")
    test_url = "https://test-url.com"
    test_content = b"test content"
    requests_mock.get(test_url, status_code=status_code, content=test_content)
    psub_client = PsubClient(test_config_file_path)

    if status_code > 200:
        with pytest.raises(click.UsageError):
            psub_client.make_request(test_url)
        return
    else:
        got_response = psub_client.make_request(test_url, content=True)

    assert got_response == {"content": test_content}


def test_scrobble(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    make_request_mock = mocker.patch.object(PsubClient, "make_request")
    psub_client = PsubClient(test_config_file_path)
    song_id = "test1234"
    psub_client.scrobble(song_id)

    make_request_mock.assert_called_once()

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)
    params = parse_qs(parsed_url.query)

    assert "scrobble" in parsed_url.path
    assert params["id"] == [song_id]


def test_get_cover_art_no_cover_in_track_data(
    mocker, test_config_file_path, config_file
):
    mocker.patch.object(PsubClient, "set_player")
    track_data = {}
    psub_client = PsubClient(test_config_file_path)
    psub_client.no_cover = b"no cover"
    psub_client.get_cover_art(track_data)
    assert os.path.exists("/tmp/art.jpg")

    with open("/tmp/art.jpg", "rb") as cover_f:
        assert cover_f.read() == psub_client.no_cover


def test_get_cover_art_happy(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    cover = b"test cover"
    make_request_mock = mocker.patch.object(
        PsubClient, "make_request", return_value={"content": cover}
    )
    track_data = {"coverArt": 123}
    psub_client = PsubClient(test_config_file_path)
    psub_client.get_cover_art(track_data)
    assert os.path.exists("/tmp/art.jpg")

    with open("/tmp/art.jpg", "rb") as cover_f:
        assert cover_f.read() == cover

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)
    params = parse_qs(parsed_url.query)

    assert "getCoverArt" in called_url
    assert params["id"] == [str(track_data["coverArt"])]
    assert params["size"] == [str(psub_client.image_size)]


def test_get_cover_art_bad_api(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    make_request_mock = mocker.patch.object(
        PsubClient, "make_request", return_value=None
    )
    track_data = {"coverArt": 123}
    psub_client = PsubClient(test_config_file_path)
    psub_client.no_cover = b"no cover"
    psub_client.get_cover_art(track_data)
    assert os.path.exists("/tmp/art.jpg")

    with open("/tmp/art.jpg", "rb") as cover_f:
        assert cover_f.read() == psub_client.no_cover


@pytest.mark.parametrize("has_results", [True, False])
def test_search(mocker, test_config_file_path, config_file, has_results):
    mocker.patch.object(PsubClient, "set_player")
    make_request_mock = mocker.patch.object(PsubClient, "make_request")
    results = ["result_1", "result_2"]

    if has_results:
        make_request_mock.return_value = {
            "subsonic-response": {"searchResult3": results}
        }
    else:
        make_request_mock.return_value = None

    psub_client = PsubClient(test_config_file_path)
    query = "test_query"
    got_results = psub_client.search(query)

    if has_results:
        assert got_results == results
    else:
        assert got_results == []

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)
    params = parse_qs(parsed_url.query)

    assert "search3" in parsed_url.path
    assert params["query"] == [query]


@pytest.mark.parametrize("has_artists", [True, False])
def test_get_artists(mocker, test_config_file_path, config_file, has_artists):
    mocker.patch.object(PsubClient, "set_player")
    make_request_mock = mocker.patch.object(PsubClient, "make_request")
    artists = ["aphex twin", "tina turner"]

    if has_artists:
        make_request_mock.return_value = {
            "subsonic-response": {"artists": {"index": artists}}
        }
    else:
        make_request_mock.return_value = None

    psub_client = PsubClient(test_config_file_path)
    got_artists = psub_client.get_artists()

    if has_artists:
        assert got_artists == artists
    else:
        assert got_artists == []

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)

    assert "getArtists" in parsed_url.path


@pytest.mark.parametrize("has_playlists", [True, False])
def test_get_playlists(mocker, test_config_file_path, config_file, has_playlists):
    mocker.patch.object(PsubClient, "set_player")
    make_request_mock = mocker.patch.object(PsubClient, "make_request")
    playlists = ["playlist_1", "playlist_2"]

    if has_playlists:
        make_request_mock.return_value = {
            "subsonic-response": {"playlists": {"playlist": playlists}}
        }
    else:
        make_request_mock.return_value = None

    psub_client = PsubClient(test_config_file_path)
    got_playlists = psub_client.get_playlists()

    if has_playlists:
        assert got_playlists == playlists
    else:
        assert got_playlists == []

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)

    assert "getPlaylists" in parsed_url.path


@pytest.mark.parametrize("has_music_folders", [True, False])
def test_get_music_folders(
    mocker, test_config_file_path, config_file, has_music_folders
):
    mocker.patch.object(PsubClient, "set_player")
    make_request_mock = mocker.patch.object(PsubClient, "make_request")
    music_folders = ["folder_1", "folder_2"]

    if has_music_folders:
        make_request_mock.return_value = {
            "subsonic-response": {"musicFolders": {"musicFolder": music_folders}}
        }
    else:
        make_request_mock.return_value = None

    psub_client = PsubClient(test_config_file_path)
    got_music_folders = psub_client.get_music_folders()

    if has_music_folders:
        assert got_music_folders == music_folders
    else:
        assert got_music_folders == []

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)

    assert "getMusicFolders" in parsed_url.path


@pytest.mark.parametrize("has_album_tracks", [True, False])
def test_get_album_tracks(mocker, test_config_file_path, config_file, has_album_tracks):
    mocker.patch.object(PsubClient, "set_player")
    make_request_mock = mocker.patch.object(PsubClient, "make_request")
    album_tracks = ["track_1", "track_2", "track_3"]
    album_id = 123

    if has_album_tracks:
        make_request_mock.return_value = {
            "subsonic-response": {"album": {"song": album_tracks}}
        }
    else:
        make_request_mock.return_value = None

    psub_client = PsubClient(test_config_file_path)
    got_album_tracks = psub_client.get_album_tracks(album_id)

    if has_album_tracks:
        assert got_album_tracks == album_tracks
    else:
        assert got_album_tracks == []

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)
    params = parse_qs(parsed_url.query)

    assert "getAlbum" in parsed_url.path
    assert params["id"] == [str(album_id)]


@pytest.mark.parametrize("music_folder_id", [None, 123])
# @pytest.mark.parametrize('has_random_songs', [True, False])
def test_play_random_songs_happy(
    mocker, test_config_file_path, config_file, music_folder_id
):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    return_values = [True] * random.randint(3, 15) + [False]
    play_stream_mock.side_effect = return_values

    make_request_mock = mocker.patch.object(PsubClient, "make_request")
    random_songs = [{"name": "song_1"}, {"name": "song_2"}, {"name": "song_3"}]

    make_request_mock.return_value = {
        "subsonic-response": {"randomSongs": {"song": random_songs}}
    }

    psub_client = PsubClient(test_config_file_path)
    psub_client.play_random_songs(music_folder_id)

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)

    assert "getRandomSongs" in parsed_url.path

    if music_folder_id is not None:
        params = parse_qs(parsed_url.query)
        assert params["musicFolderId"] == [str(music_folder_id)]

    assert play_stream_mock.call_count == len(return_values)


@pytest.mark.parametrize("music_folder_id", [None, 123])
def test_play_random_songs_bad_api(
    mocker, test_config_file_path, config_file, music_folder_id
):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    return_values = [True] * random.randint(3, 15) + [False]
    play_stream_mock.side_effect = return_values
    make_request_mock = mocker.patch.object(
        PsubClient, "make_request", return_value=None
    )

    psub_client = PsubClient(test_config_file_path)

    make_request_mock.return_value = None

    with pytest.raises(click.ClickException):
        psub_client.play_random_songs(music_folder_id)


def test_play_radio_happy(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    play_stream_mock.side_effect = [True, True, False]

    make_request_mock = mocker.patch.object(PsubClient, "make_request")
    radio_songs = [{"name": "song_1"}, {"name": "song_2"}, {"name": "song_3"}]
    make_request_mock.return_value = {
        "subsonic-response": {"similarSongs2": {"song": radio_songs}}
    }
    radio_id = 123

    psub_client = PsubClient(test_config_file_path)
    psub_client.play_radio(radio_id)

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)
    params = parse_qs(parsed_url.query)

    assert params["id"] == [str(radio_id)]
    assert "getSimilarSongs2" in parsed_url.path

    assert play_stream_mock.call_count == len(radio_songs)


def test_play_radio_bad_api(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    play_stream_mock.side_effect = [True, True, False]

    mocker.patch.object(PsubClient, "make_request", return_value=None)

    radio_id = 123
    psub_client = PsubClient(test_config_file_path)

    with pytest.raises(click.ClickException):
        psub_client.play_radio(radio_id)


@pytest.mark.parametrize(
    "randomise, invert_random, shuffle_calls",
    ([True, False, 1], [True, True, 0], [False, False, 0], [False, True, 1]),
)
def test_play_artist(
    mocker, test_config_file_path, config_file, randomise, invert_random, shuffle_calls
):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    play_stream_mock.side_effect = [True] * 8 + [False]
    shuffle_mock = mocker.patch("client.psub.shuffle")

    albums = [{"id": 1}, {"id": 2}, {"id": 3}]
    albums_response = {"subsonic-response": {"artist": {"album": albums}}}
    make_request_mock = mocker.patch.object(
        PsubClient, "make_request", return_value=albums_response
    )
    album_songs = [{"name": "song_1"}, {"name": "song_2"}, {"name": "song_3"}]
    get_album_tracks_mock = mocker.patch.object(PsubClient, "get_album_tracks")
    get_album_tracks_mock.side_effect = [album_songs, album_songs, album_songs]

    artist_id = 123
    psub_client = PsubClient(test_config_file_path)
    psub_client.invert_random = invert_random
    psub_client.play_artist(artist_id, randomise)

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)
    params = parse_qs(parsed_url.query)

    assert params["id"] == [str(artist_id)]
    assert "getArtist" in parsed_url.path

    assert shuffle_mock.call_count == shuffle_calls
    assert get_album_tracks_mock.call_count == len(albums)
    assert play_stream_mock.call_count == 1


def test_play_artist_bad_api(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    shuffle_mock = mocker.patch("client.psub.shuffle")
    make_request_mock = mocker.patch.object(
        PsubClient, "make_request", return_value=None
    )
    # get_album_tracks_mock = mocker.patch.object(PsubClient, 'get_album_tracks', return_value=[])

    artist_id = 123
    psub_client = PsubClient(test_config_file_path)

    with pytest.raises(click.ClickException) as e:
        psub_client.play_artist(artist_id, random.choice([True, False]))

    assert "Failed to get artist info" in str(e.value)
    assert make_request_mock.call_count == 1
    assert shuffle_mock.call_count == 0
    assert play_stream_mock.call_count == 0


def test_play_artist_no_songs(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    shuffle_mock = mocker.patch("client.psub.shuffle")
    albums = [{"id": 1}, {"id": 2}, {"id": 3}]
    albums_response = {"subsonic-response": {"artist": {"album": albums}}}
    make_request_mock = mocker.patch.object(
        PsubClient, "make_request", return_value=albums_response
    )
    get_album_tracks_mock = mocker.patch.object(
        PsubClient, "get_album_tracks", return_value=[]
    )

    artist_id = 123
    psub_client = PsubClient(test_config_file_path)

    with pytest.raises(click.ClickException) as e:
        psub_client.play_artist(artist_id, random.choice([True, False]))

    assert "No songs found for artist" in str(e.value)
    assert make_request_mock.call_count == 1
    assert get_album_tracks_mock.call_count == len(albums)
    assert shuffle_mock.call_count == 0
    assert play_stream_mock.call_count == 0


@pytest.mark.parametrize(
    "randomise, invert_random, shuffle_calls",
    ([True, False, 1], [True, True, 0], [False, False, 0], [False, True, 1]),
)
def test_play_album(
    mocker, test_config_file_path, config_file, randomise, invert_random, shuffle_calls
):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    play_stream_mock.side_effect = [True, True, False]
    shuffle_mock = mocker.patch("client.psub.shuffle")

    album_songs = [{"name": "song_1"}, {"name": "song_2"}, {"name": "song_3"}]
    get_album_tracks_mock = mocker.patch.object(
        PsubClient, "get_album_tracks", return_value=album_songs
    )

    album_id = 123
    psub_client = PsubClient(test_config_file_path)
    psub_client.invert_random = invert_random
    psub_client.play_album(album_id, randomise)

    assert shuffle_mock.call_count == shuffle_calls
    assert get_album_tracks_mock.call_count == 1
    assert play_stream_mock.call_count == 1


def test_play_album_no_songs(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    play_stream_mock.side_effect = [True, True, False]
    shuffle_mock = mocker.patch("client.psub.shuffle")

    get_album_tracks_mock = mocker.patch.object(
        PsubClient, "get_album_tracks", return_value=[]
    )

    album_id = 123
    psub_client = PsubClient(test_config_file_path)
    psub_client.play_album(album_id, random.choice([True, False]))

    assert get_album_tracks_mock.call_count == 1
    assert play_stream_mock.call_count == 0
    assert shuffle_mock.call_count == 0


@pytest.mark.parametrize(
    "randomise, invert_random, shuffle_calls",
    ([True, False, 1], [True, True, 0], [False, False, 0], [False, True, 1]),
)
def test_play_playlist_happy(
    mocker, test_config_file_path, config_file, randomise, invert_random, shuffle_calls
):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    play_stream_mock.side_effect = [True, True, False]
    playlist = [{"name": "song_1"}, {"name": "song_2"}, {"name": "song_3"}]
    playlists_response = {"subsonic-response": {"playlist": {"entry": playlist}}}
    make_request_mock = mocker.patch.object(PsubClient, "make_request")
    make_request_mock.return_value = playlists_response

    shuffle_mock = mocker.patch("client.psub.shuffle")

    playlist_id = 123
    psub_client = PsubClient(test_config_file_path)
    psub_client.invert_random = invert_random
    psub_client.play_playlist(playlist_id, randomise)

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)
    params = parse_qs(parsed_url.query)

    assert params["id"] == [str(playlist_id)]
    assert "getPlaylist" in parsed_url.path

    assert shuffle_mock.call_count == shuffle_calls
    assert play_stream_mock.call_count == 1


def test_play_playlist_bad_api(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    make_request_mock = mocker.patch.object(
        PsubClient, "make_request", return_value=None
    )
    shuffle_mock = mocker.patch("client.psub.shuffle")

    playlist_id = 123
    psub_client = PsubClient(test_config_file_path)
    psub_client.play_playlist(playlist_id, random.choice([True, False]))

    called_url = make_request_mock.call_args.kwargs["url"]
    parsed_url = urlparse(called_url)
    params = parse_qs(parsed_url.query)

    assert params["id"] == [str(playlist_id)]
    assert "getPlaylist" in parsed_url.path

    assert shuffle_mock.call_count == 0
    assert play_stream_mock.call_count == 0


class PlayerTest(PsubPlayer):
    def __init__(self, player_config: Dict):
        super().__init__(player_config)
        self.playing = False
        self.test_stop = player_config.get("test_stop", False)

    def play(self, track_data: Dict):
        super().play(track_data)
        self.playing = True

        if self.test_stop:
            threading.Timer(0.1, self.stop).start()

    def is_playing(self):
        return self.playing

    def stop(self):
        super().stop()
        self.playing = False


@pytest.mark.parametrize("notify", [True, False])
def test_play_stream_happy(mocker, test_config_file_path, config_file, notify):
    mocker.patch.object(PsubClient, "set_player")
    mocker.patch.object(click, "getchar")
    scrobble_mock = mocker.patch.object(PsubClient, "scrobble")
    commands_mock = mocker.patch.object(PsubClient, "commands")
    play_stream_spy = mocker.spy(PsubClient, "play_stream")
    get_cover_art_mock = mocker.patch.object(PsubClient, "get_cover_art")
    psub_client = PsubClient(test_config_file_path)
    show_notification_mock = mocker.patch.object(
        psub_client.notifications, "show_notification"
    )
    psub_client.notify = notify
    psub_client.player = PlayerTest({"test_stop": True})
    psub_client.track_list = [{"id": 1}, {"id": 2}]
    response = psub_client.play_stream(0)

    assert response is True
    assert psub_client.track_index == len(psub_client.track_list)
    assert scrobble_mock.call_count == len(psub_client.track_list)
    assert commands_mock.call_count == 0
    assert play_stream_spy.call_count == len(psub_client.track_list) + 1

    if notify:
        assert get_cover_art_mock.call_count == len(psub_client.track_list)
        assert show_notification_mock.call_count == len(psub_client.track_list)
    else:
        assert get_cover_art_mock.call_count == 0
        assert show_notification_mock.call_count == 0


def test_play_stream_with_input(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    mocker.patch.object(PsubClient, "add_input")
    mocker.patch.object(click, "getchar")
    mocker.patch.object(PsubClient, "scrobble")
    mocker.patch.object(PsubClient, "get_cover_art")
    psub_client = PsubClient(test_config_file_path)
    mocker.patch.object(psub_client.notifications, "show_notification")
    psub_client.notify = False
    psub_client.input_queue.put_nowait("t")
    psub_client.player = PlayerTest({})
    psub_client.player.playing = True
    psub_client.track_list = [{"id": 1}, {"id": 2}]

    commands_mock = mocker.patch.object(PsubClient, "commands")
    commands_mock.side_effect = [None, None, None, False]
    response = psub_client.play_stream(0)

    assert response is False
    assert commands_mock.call_count == 4
    psub_client.player.stop()


@pytest.mark.parametrize(
    "param, value, expected_print, expected_index",
    [
        ("previous", "p", ":last_track_button:  [blue]Previous track[/]", 1),
        ("next", "n", ":next_track_button:  [blue]Next track[/]", 3),
        ("restart", "b", ":repeat_button: [blue]Restarting track[/]", 2),
    ],
)
def test_commands_controls(
    mocker,
    test_config_file_path,
    config_file,
    param,
    value,
    expected_print,
    expected_index,
):
    mocker.patch.object(PsubClient, "set_player")
    print_mock = mocker.patch("client.psub.print")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    player = PsubPlayer({})
    stop_mock = mocker.patch.object(player, "stop")
    psub_client = PsubClient(test_config_file_path)
    setattr(psub_client, param, value)
    psub_client.scan_input = True
    psub_client.player = player
    psub_client.track_index = 2
    psub_client.input_queue.put_nowait(value)
    psub_client.commands()

    assert stop_mock.call_count == 1
    print_mock.assert_has_calls([call(expected_print)])
    play_stream_mock.assert_has_calls([call(expected_index)])
    assert psub_client.scan_input is True


def test_commands_exit(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    print_mock = mocker.patch("client.psub.print")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    player = PsubPlayer({})
    stop_mock = mocker.patch.object(player, "stop")
    psub_client = PsubClient(test_config_file_path)
    value = "x"
    psub_client.scan_input = True
    psub_client.exit = value
    psub_client.player = player
    psub_client.track_index = 2
    psub_client.input_queue.put_nowait(value)
    resp = psub_client.commands()

    assert resp is False
    assert stop_mock.call_count == 1
    print_mock.assert_has_calls([call(":cross_mark: [red]Exiting[/]")])
    assert play_stream_mock.call_count == 0
    assert psub_client.scan_input is False


def test_commands_unknown(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    print_mock = mocker.patch("client.psub.print")
    play_stream_mock = mocker.patch.object(PsubClient, "play_stream")
    player = PsubPlayer({})
    stop_mock = mocker.patch.object(player, "stop")
    psub_client = PsubClient(test_config_file_path)
    value = "x"
    psub_client.scan_input = True
    psub_client.exit = value
    psub_client.player = player
    psub_client.track_index = 2
    psub_client.input_queue.put_nowait("value")
    resp = psub_client.commands()

    assert resp is None
    assert stop_mock.call_count == 0
    assert print_mock.call_count == 0
    assert psub_client.scan_input is True
    assert play_stream_mock.call_count == 0


def test_add_input_no_lock(mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    sleep_mock = mocker.patch.object(time, "sleep")
    psub_client = PsubClient(test_config_file_path)
    getchar_mock = mocker.patch.object(click, "getchar")
    psub_client.scan_input = True

    def stop():
        psub_client.scan_input = False

    threading.Timer(0.2, stop).start()
    psub_client.add_input()

    assert sleep_mock.call_count > 0
    assert getchar_mock.call_count == 0


def test_add_input_with_lock(mocker, test_config_file_path, config_file):
    open(os.path.join(click.get_app_dir("pSub"), "play.lock"), "w+").close()
    mocker.patch.object(PsubClient, "set_player")
    sleep_mock = mocker.patch.object(time, "sleep")
    getchar_mock = mocker.patch.object(click, "getchar")
    psub_client = PsubClient(test_config_file_path)
    psub_client.scan_input = True

    def stop():
        psub_client.scan_input = False

    threading.Timer(0.2, stop).start()
    psub_client.add_input()

    assert sleep_mock.call_count > 0
    assert getchar_mock.call_count > 0


def test_show_banner(mocker, test_config_file_path, config_file):
    clear_mock = mocker.patch.object(click, "clear")
    print_mock = mocker.patch("client.psub.print")
    mocker.patch.object(PsubClient, "set_player")
    psub_client = PsubClient(test_config_file_path)
    psub_client.previous = "test_previous"
    psub_client.next = "test_next"
    psub_client.restart = "test_restart"
    psub_client.exit = "test_exit"
    test_message = "test_message"
    psub_client.show_banner(test_message)

    assert clear_mock.call_count == 1
    assert print_mock.call_count == 5

    print_mock.assert_has_calls(
        [
            call(f"\n:musical_note:   [bold blue]{test_message}[/]   :musical_note:\n"),
            call(
                f"[bold yellow]{psub_client.previous} = :last_track_button:  Previous track[/]"
            ),
            call(
                f"[bold yellow]{psub_client.next} = :next_track_button:  Next track[/]"
            ),
            call(
                f"[bold yellow]{psub_client.restart} = :repeat_button: Restart track[/]"
            ),
            call(f"[bold yellow]{psub_client.exit} = :cross_mark: Exit[/]\n"),
        ]
    )


def test_set_default_config(tmp_path, mocker, test_config_file_path, config_file):
    mocker.patch.object(PsubClient, "set_player")
    psub_client = PsubClient(test_config_file_path)
    config_path = os.path.join(tmp_path, "config.yaml")
    psub_client.set_default_config(config_path)
    assert os.path.exists(config_path)
