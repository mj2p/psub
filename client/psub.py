import fnmatch
import hashlib
import inspect
import os
import string
import sys
import time
from importlib import import_module
from queue import LifoQueue
from random import SystemRandom, shuffle
from threading import Thread
from typing import Dict, List, Optional, Tuple

import requests
import rich_click as click
import urllib3
import yaml
from packaging import version
from rich import print

urllib3.disable_warnings()


class PsubClient(object):
    """
    pSub Object interfaces with the Subsonic server and handles streaming media
    """

    def __init__(self, config_file_path: str) -> None:
        """
        Load the config, creating it if it doesn't exist.
        Test server connection
        Start background thread for getting user input during streaming
        """
        # If no config file exists we should create one and
        if not os.path.isfile(config_file_path):
            self.set_default_config(config_file_path)
            click.secho("Welcome to pSub", fg="green")
            click.secho("To get set up, please edit your config file", fg="red")
            click.pause()
            click.edit(filename=config_file_path)

        # load the config file
        with open(config_file_path) as config_file:
            config = yaml.safe_load(config_file)

        # Get the Server Config
        server_config = config.get("server", {})
        self.host = server_config.get("host")
        self.username = server_config.get("username", "")
        self.password = server_config.get("password", "")
        self.api = server_config.get("api", "1.16.1")
        self.ssl = server_config.get("ssl", False)
        self.verify_ssl = server_config.get("verify_ssl", True)

        # internal variables
        self.search_results = []

        # get the streaming config
        streaming_config = config.get("streaming", {})
        self.format = streaming_config.get("format", "raw")
        self.invert_random = streaming_config.get("invert_random", False)
        self.notify = streaming_config.get("notify", True)
        self.image_size = streaming_config.get("image_size", 512)

        # map the controls:
        controls_config = streaming_config.get("controls", {})
        self.next = str(controls_config.get("next", "n"))
        self.previous = str(controls_config.get("previous", "p"))
        self.restart = str(controls_config.get("restart", "b"))
        self.exit = str(controls_config.get("exit", "x"))

        # set the player
        self.player = None
        player = streaming_config.get("player", "ffplay")
        player_config = streaming_config.get(player, {})
        self.set_player(player, player_config)

        if self.notify:
            from client.notifications import Notifications

            self.notifications = Notifications()

        # use a Queue to handle command input while a file is playing.
        # set the thread going now
        self.input_queue = LifoQueue()
        self.scan_input = True
        input_thread = Thread(target=self.add_input, name="add_input")
        input_thread.daemon = True
        input_thread.start()

        self.track_list = []
        self.track_index = 0

        # remove the lock file if one exists
        if os.path.isfile(
            os.path.join(click.get_app_dir("pSub"), "play.lock")
        ):  # pragma: no cover
            os.remove(os.path.join(click.get_app_dir("pSub"), "play.lock"))

        # set up missing cover art
        with open(
            os.path.join(os.path.dirname(os.path.realpath(__file__)), "no_cover.jpg"),
            "rb",
        ) as no_cover:
            self.no_cover = no_cover.read()

    def set_player(self, player: str, player_config: Dict) -> None:
        """
        Plug and play Players.
        subclasses of players.base_player.PsubPlayer exist in the `players` module.
        Inspect them and load them if they match the requested player string
        (player files and classes need to be named the same as the "player" config option)
        """
        try:
            import_module(f"players.{player}")

            for obj in inspect.getmembers(
                sys.modules[f"players.{player}"], inspect.isclass
            ):
                if obj[0].lower() == player:
                    self.player = obj[1](player_config)
        except ModuleNotFoundError:
            pass

        if self.player is None:
            available_players = "\n".join(
                sorted(
                    [
                        f"  {p.split('.')[0]}"
                        for p in fnmatch.filter(os.listdir("players"), "*.py")
                        if p not in ["base_player.py", "__init__.py"]
                    ]
                )
            )
            raise click.UsageError(
                f"Unable to load a player matching '{player}'.\n"
                "Available options are:\n"
                f"{available_players}\n\n"
                "Please adjust your config file by running:\n"
                "  psub -c"
            )

        click.secho(f"Playing with {player}", fg="yellow")

    def test_config(self) -> None:
        """
        Ping the server specified in the config to ensure we can communicate
        """
        click.secho("Testing Server Connection", fg="green")
        click.secho(
            f"{'https' if self.ssl else 'http'}://{self.username}@{self.host}",
            fg="blue",
        )
        ping = self.make_request(url=self.create_url("ping"))

        if ping:
            click.secho("Test Passed", fg="green")
        else:
            raise click.ClickException("Test Failed!\n" "Please check your config")

    def hash_password(self) -> Tuple[str, str]:
        """
        return random salted md5 hash of password
        """
        characters = string.ascii_uppercase + string.ascii_lowercase + string.digits
        salt = "".join(SystemRandom().choice(characters) for _ in range(9))  # noqa
        salted_password = self.password + salt
        token = hashlib.md5(salted_password.encode("utf-8")).hexdigest()
        return token, salt

    def create_url(self, endpoint: str) -> str:
        """
        build the standard url for interfacing with the Subsonic REST API
        :param endpoint: REST endpoint to incorporate in the url
        """
        proto = "https" if self.ssl else "http"

        if version.parse(self.api) < version.parse("1.13.0"):
            return (
                f"{proto}://{self.host}/rest/{endpoint}.view?"
                f"u={self.username}&"
                f"p={self.password}&"
                f"v={self.api}&c=pSub&f=json"
            )
        else:
            token, salt = self.hash_password()
            return (
                f"{proto}://{self.host}/rest/{endpoint}?"
                f"u={self.username}&"
                f"t={token}&"
                f"s={salt}&"
                f"v={self.api}&c=pSub&f=json"
            )

    def make_request(self, url: str, content: bool = False) -> Optional[Dict]:
        """
        GET the supplied url and return the response as a dictionary.
        Handle any errors present.
        :param url: full url to call. see create_url method for details
        :param content: boolean to indicate that we want the r.content returned instead of json
        :return: Subsonic response or None on failure
        """
        try:
            r = requests.get(url=url, verify=self.verify_ssl)
        except requests.exceptions.ConnectionError as e:
            raise click.UsageError(f"A request to the url {url} failed: {e}")

        if r.status_code != requests.codes.ok:
            raise click.UsageError(
                f"Got a bad response from the url {url}: {r.status_code} {r.reason}"
            )

        if content:
            return {"content": r.content}

        try:
            response = r.json()
        except ValueError:
            response = {
                "subsonic-response": {
                    "error": {"code": 100, "message": r.text},
                    "status": "failed",
                }
            }

        subsonic_response = response.get("subsonic-response", {})
        status = subsonic_response.get("status", "failed")

        if status == "failed":
            error = subsonic_response.get("error", {})
            click.secho(
                f"Command Failed! {url} - {error.get('code', '')} {error.get('message', '')}",
                fg="red",
            )
            return None

        return response

    def scrobble(self, song_id):
        """
        notify the Subsonic server that a track is being played within pSub
        :param song_id:
        :return:
        """
        self.make_request(url=f"{self.create_url('scrobble')}&id={song_id}")

    def get_cover_art(self, track_data):
        cover_base_url = self.create_url("getCoverArt")
        cover_art = track_data.get("coverArt")

        if cover_art is None:
            cover = self.no_cover
        else:
            cover_url = f"{cover_base_url}&id={cover_art}&size={self.image_size}"
            cover_resp = self.make_request(url=cover_url, content=True)

            if cover_resp is None:
                cover = self.no_cover
            else:
                cover = cover_resp["content"]

        with open("/tmp/art.jpg", "wb") as cover_f:
            cover_f.write(cover)

    def search(self, query):
        """
        search using query and return the result
        :return:
        :param query: search term string
        """
        results = self.make_request(url=f"{self.create_url('search3')}&query={query}")

        if results is not None:
            return results["subsonic-response"].get("searchResult3", [])

        return []

    def get_artists(self):
        """
        Gather list of Artists from the Subsonic server
        :return: list
        """
        artists = self.make_request(url=self.create_url("getArtists"))

        if artists is not None:
            return artists["subsonic-response"].get("artists", {}).get("index", [])

        return []

    def get_playlists(self):
        """
        Get a list of available playlists from the server
        :return:
        """
        playlists = self.make_request(url=self.create_url("getPlaylists"))

        if playlists is not None:
            return (
                playlists["subsonic-response"].get("playlists", {}).get("playlist", [])
            )

        return []

    def get_music_folders(self):
        """
        Gather list of Music Folders from the Subsonic server
        :return: list
        """
        music_folders = self.make_request(url=self.create_url("getMusicFolders"))

        if music_folders is not None:
            return (
                music_folders["subsonic-response"]
                .get("musicFolders", {})
                .get("musicFolder", [])
            )

        return []

    def get_album_tracks(self, album_id: int) -> List:
        """
        return a list of album track ids for the given album id
        :param album_id: id of the album
        :return: list
        """
        album_info = self.make_request(
            url=f'{self.create_url("getAlbum")}&id={album_id}'
        )

        if album_info is not None:
            return album_info["subsonic-response"].get("album", {}).get("song", [])
        else:
            return []

    def play_random_songs(self, music_folder_id: Optional[int] = None) -> None:
        """
        Gather random tracks from the Subsonic server and play them endlessly
        :param music_folder_id: integer denoting music folder to filter tracks
        """
        playing = True
        self.track_index = 0

        while playing:
            url = self.create_url("getRandomSongs")

            if music_folder_id is not None:
                url = f"{url}&musicFolderId={music_folder_id}"

            random_songs = self.make_request(url=url)

            if not random_songs:
                raise click.ClickException("Failed to get random tracks")

            # track_list = random_songs['subsonic-response'].get('randomSongs', {}).get('song', [])
            # self.play(track_list)
            self.track_list += (
                random_songs["subsonic-response"].get("randomSongs", {}).get("song", [])
            )
            playing = self.play_stream(self.track_index)

    def play_radio(self, radio_id: int) -> None:
        """
        Get songs similar to the supplied Artist id and play them endlessly
        :param radio_id: id of Artist
        """
        playing = True
        self.track_index = 0

        while playing:
            radio_track_list = self.make_request(
                url="{}&id={}".format(self.create_url("getSimilarSongs2"), radio_id)
            )

            if not radio_track_list:
                raise click.ClickException("Failed to get radio tracks")

            self.track_list += radio_track_list["subsonic-response"][
                "similarSongs2"
            ].get("song", [])
            playing = self.play_stream(self.track_index)

    def play_artist(self, artist_id: int, randomise: bool) -> None:
        """
        Get the songs by the given artist_id and play them
        :param artist_id:  id of the artist to play
        :param randomise: if True, randomise the playback order
        """
        artist_info = self.make_request(
            url="{}&id={}".format(self.create_url("getArtist"), artist_id)
        )
        songs = []

        if artist_info is None:
            raise click.ClickException("Failed to get artist info")

        for artist_album in artist_info["subsonic-response"]["artist"]["album"]:
            songs += self.get_album_tracks(artist_album.get("id"))

        if not songs:
            raise click.ClickException("No songs found for artist")

        if self.invert_random:
            randomise = not randomise

        if randomise:
            shuffle(songs)

        self.track_list = songs
        self.play_stream(0)

    def play_album(self, album_id, randomise):
        """
        Get the songs for the given album id and play them
        :param album_id:
        :param randomise:
        :return:
        """
        songs = self.get_album_tracks(album_id)

        if not songs:
            return

        if self.invert_random:
            randomise = not randomise

        if randomise:
            shuffle(songs)

        self.track_list = songs
        self.play_stream(0)

    def play_playlist(self, playlist_id: int, randomise: bool) -> None:
        """
        Get the tracks from the supplied playlist id and play them
        :param playlist_id:
        :param randomise:
        :return:
        """
        playlist_info = self.make_request(
            url=f"{self.create_url('getPlaylist')}&id={playlist_id}"
        )

        if not playlist_info:
            return

        songs = playlist_info["subsonic-response"]["playlist"]["entry"]

        if self.invert_random:
            randomise = not randomise

        if randomise:
            shuffle(songs)

        self.track_list = songs
        self.play_stream(0)

    def get_playlist(self, track_list: List[Dict]) -> List:
        return [
            f"{self.create_url('download')}&id={track.get('id')}&format={self.format}"
            for track in track_list
        ]

    def play(self, track_list):
        self.player.load_playlist(self.get_playlist(track_list))
        self.player.play(track_list[0])

    def play_stream(self, track_index: int) -> bool:
        """
        Play the track at the track_index position of self.track_list in the configured player.
        While stream is playing allow user input to control playback.
        :param: track_index int
        :return:
        """
        self.track_index = track_index if track_index >= 0 else 0

        if self.track_index == len(self.track_list):
            # for infinite play, we want the loop to keep going
            return True

        track_data = self.track_list[self.track_index]
        track_id = track_data.get("id")
        track_data[
            "stream_url"
        ] = f"{self.create_url('stream')}&id={track_id}&format={self.format}"

        if self.notify:
            self.get_cover_art(track_data)
            self.notifications.show_notification(track_data)

        self.player.play(track_data)
        self.scrobble(track_id)

        while self.player.is_playing():
            if self.input_queue.empty():
                time.sleep(0.2)
                continue

            command = self.commands()

            if isinstance(command, bool):
                return command

        return self.play_stream(self.track_index + 1)

    def commands(self) -> Optional[bool]:
        command = self.input_queue.get_nowait()
        self.input_queue.queue.clear()

        if self.previous in command.lower():
            print(":last_track_button: [blue] Previous track[/]")
            click.echo("\r", nl=False)
            self.player.stop()
            return self.play_stream(self.track_index - 1)

        if self.next in command.lower():
            print(":next_track_button: [blue]Next track[/]")
            click.echo("\r", nl=False)
            self.player.stop()
            return self.play_stream(self.track_index + 1)

        if self.restart in command.lower():
            print(":repeat_button: [blue]Restarting track[/]")
            click.echo("\r", nl=False)
            self.player.stop()
            return self.play_stream(self.track_index)

        if self.exit in command.lower():
            print(":cross_mark: [red]Exiting[/]")
            click.echo("\r", nl=False)
            self.scan_input = False
            self.player.stop()
            time.sleep(0.5)
            return False

    def add_input(self) -> None:
        """
        This method runs in a separate thread (started in __init__).
        When the play.lock file exists it waits for user input and writes it to a Queue for further processing.
        """
        while self.scan_input:
            time.sleep(0.2)

            if not os.path.isfile(os.path.join(click.get_app_dir("pSub"), "play.lock")):
                continue

            self.input_queue.put_nowait(click.getchar())

    def show_banner(self, message: str) -> None:
        """
        Show a standardized banner with custom message and controls for playback
        :param message:
        """
        click.clear()
        print(f"\n:musical_note:   [bold blue]{message}[/]   :musical_note:\n")
        print(f"[bold yellow]{self.previous} = Previous track :last_track_button: [/]")
        print(f"[bold yellow]{self.next} = Next track :next_track_button: [/]")
        print(f"[bold yellow]{self.restart} = Restart track :repeat_button: [/]")
        print(f"[bold yellow]{self.exit} = Exit :cross_mark: [/]\n")

    @staticmethod
    def set_default_config(config_file_path: str) -> None:
        """
        When no config file is detected, this method is run to write the default config
        """
        with open("config.yaml.j2") as template:
            with open(config_file_path, "w+") as config_file:
                config_file.write(template.read())
