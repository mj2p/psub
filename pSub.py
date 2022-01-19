import hashlib
import os
import string
import sys
import time
from random import SystemRandom, shuffle
from subprocess import CalledProcessError, Popen
from threading import Thread
from typing import Dict, List, Union

import questionary
import requests
from click import UsageError
from packaging import version

from queue import LifoQueue

import click
import yaml
import urllib3
urllib3.disable_warnings()


class pSub(object):
    """
    pSub Object interfaces with the Subsonic server and handles streaming media
    """
    def __init__(self, config):
        """
        Load the config, creating it if it doesn't exist.
        Test server connection
        Start background thread for getting user input during streaming
        :param config: path to config yaml file
        """
        # If no config file exists we should create one and
        if not os.path.isfile(config):
            self.set_default_config(config)
            click.secho('Welcome to pSub', fg='green')
            click.secho('To get set up, please edit your config file', fg='red')
            click.pause()
            click.edit(filename=config)

        # load the config file
        with open(config) as config_file:
            config = yaml.safe_load(config_file)

        # Get the Server Config
        server_config = config.get('server', {})
        self.host = server_config.get('host')
        self.username = server_config.get('username', '')
        self.password = server_config.get('password', '')
        self.api = server_config.get('api', '1.16.0')
        self.ssl = server_config.get('ssl', False)
        self.verify_ssl = server_config.get('verify_ssl', True)

        # internal variables
        self.search_results = []

        # get the streaming config
        streaming_config = config.get('streaming', {})
        self.format = streaming_config.get('format', 'raw')
        self.display = streaming_config.get('display', False)
        self.show_mode = streaming_config.get('show_mode', 0)
        self.invert_random = streaming_config.get('invert_random', False)
        self.notify = streaming_config.get('notify', True)

        if self.notify:
            import notifications
            self.notifications = notifications.Notifications(self)

        # use a Queue to handle command input while a file is playing.
        # set the thread going now
        self.input_queue = LifoQueue()
        input_thread = Thread(target=self.add_input)
        input_thread.daemon = True
        input_thread.start()

        # remove the lock file if one exists
        if os.path.isfile(os.path.join(click.get_app_dir('pSub'), 'play.lock')):
            os.remove(os.path.join(click.get_app_dir('pSub'), 'play.lock'))
        client_config = config.get('client', {})
        self.pre_exe = client_config.get('pre_exe', '')
        self.pre_exe = self.pre_exe.split(' ') if self.pre_exe is not '' else []

    def test_config(self):
        """
        Ping the server specified in the config to ensure we can communicate
        """
        click.secho('Testing Server Connection', fg='green')
        click.secho(
            '{}://{}@{}'.format(
                'https' if self.ssl else 'http',
                self.username,
                self.host,
            ),
            fg='blue'
        )
        ping = self.make_request(url=self.create_url('ping'))
        if ping:
            click.secho('Test Passed', fg='green')
            return True
        else:
            click.secho('Test Failed! Please check your config', fg='black', bg='red')
            return False

    def hash_password(self):
        """
        return random salted md5 hash of password
        """
        characters = string.ascii_uppercase + string.ascii_lowercase + string.digits
        salt = ''.join(SystemRandom().choice(characters) for i in range(9))  # noqa
        salted_password = self.password + salt
        token = hashlib.md5(salted_password.encode('utf-8')).hexdigest()
        return token, salt

    def create_url(self, endpoint):
        """
        build the standard url for interfacing with the Subsonic REST API
        :param endpoint: REST endpoint to incorporate in the url
        """
        token, salt = self.hash_password()
        if version.parse(self.api) < version.parse("1.13.0"):
            url = '{}://{}/rest/{}.view?u={}&p={}&v={}&c=pSub&f=json'.format(
                'https' if self.ssl else 'http',
                self.host,
                endpoint,
                self.username,
                self.password,
                self.api
            )
        else:
            url = '{}://{}/rest/{}?u={}&t={}&s={}&v={}&c=pSub&f=json'.format(
            'https' if self.ssl else 'http',
            self.host,
            endpoint,
            self.username,
            token,
            salt,
            self.api
        )
            
        return url

    def make_request(self, url):
        """
        GET the supplied url and resturn the response as json.
        Handle any errors present.
        :param url: full url. see create_url method for details
        :return: Subsonic response or None on failure
        """
        try:
            r = requests.get(url=url, verify=self.verify_ssl)
        except requests.exceptions.ConnectionError as e:
            click.secho('{}'.format(e), fg='red')
            sys.exit(1)

        try:
            response = r.json()
        except ValueError:
            response = {
                'subsonic-response': {
                    'error': {
                        'code': 100,
                        'message': r.text
                    },
                    'status': 'failed'
                }
            }

        subsonic_response = response.get('subsonic-response', {})
        status = subsonic_response.get('status', 'failed')

        if status == 'failed':
            error = subsonic_response.get('error', {})
            click.secho(
                'Command Failed! {}: {}'.format(
                    error.get('code', ''),
                    error.get('message', '')
                ),
                fg='red'
            )
            return None

        return response

    def scrobble(self, song_id):
        """
        notify the Subsonic server that a track is being played within pSub
        :param song_id:
        :return:
        """
        self.make_request(
            url='{}&id={}'.format(
                self.create_url('scrobble'),
                song_id
            )
        )

    def search(self, query):
        """
        search using query and return the result
        :return:
        :param query: search term string
        """
        results = self.make_request(
            url='{}&query={}'.format(self.create_url('search3'), query)
        )
        if results:
            return results['subsonic-response'].get('searchResult3', [])
        return []

    def get_artists(self):
        """
        Gather list of Artists from the Subsonic server
        :return: list
        """
        artists = self.make_request(url=self.create_url('getArtists'))
        if artists:
            return artists['subsonic-response']['artists'].get('index', [])
        return []

    def get_playlists(self):
        """
        Get a list of available playlists from the server
        :return:
        """
        playlists = self.make_request(url=self.create_url('getPlaylists'))
        if playlists:
            return playlists['subsonic-response']['playlists'].get('playlist', [])
        return []

    def get_music_folders(self):
        """
        Gather list of Music Folders from the Subsonic server
        :return: list
        """
        music_folders = self.make_request(url=self.create_url('getMusicFolders'))
        if music_folders:
            return music_folders['subsonic-response']['musicFolders'].get('musicFolder', [])
        return []

    def get_album_tracks(self, album_id):
        """
        return a list of album track ids for the given album id
        :param album_id: id of the album
        :return: list
        """
        album_info = self.make_request('{}&id={}'.format(self.create_url('getAlbum'), album_id))
        songs = []

        for song in album_info['subsonic-response']['album'].get('song', []):
            songs.append(song)

        return songs

    def play_random_songs(self, music_folder):
        """
        Gather random tracks from the Subsonic server and play them endlessly
        :param music_folder: integer denoting music folder to filter tracks
        """
        url = self.create_url('getRandomSongs')
        
        if music_folder is not None:
            url = '{}&musicFolderId={}'.format(url, music_folder)

        playing = True

        while playing:
            random_songs = self.make_request(url)

            if not random_songs:
                return

            for random_song in random_songs['subsonic-response']['randomSongs'].get('song', []):
                if not playing:
                    return
                playing = self.play_stream(dict(random_song))

    def play_radio(self, radio_id):
        """
        Get songs similar to the supplied id and play them endlessly
        :param radio_id: id of Artist
        """
        playing = True
        while playing:
            similar_songs = self.make_request(
                '{}&id={}'.format(self.create_url('getSimilarSongs2'), radio_id)
            )

            if not similar_songs:
                return

            for radio_track in similar_songs['subsonic-response']['similarSongs2'].get('song', []):
                if not playing:
                    return
                playing = self.play_stream(dict(radio_track))

    def play_artist(self, artist_id, randomise):
        """
        Get the songs by the given artist_id and play them
        :param artist_id:  id of the artist to play
        :param randomise: if True, randomise the playback order
        """
        artist_info = self.make_request('{}&id={}'.format(self.create_url('getArtist'), artist_id))
        songs = []

        for album in artist_info['subsonic-response']['artist']['album']:
            songs += self.get_album_tracks(album.get('id'))

        if self.invert_random:
            randomise = not randomise

        if randomise:
            shuffle(songs)

        playing = True

        while playing:
            for song in songs:
                if not playing:
                    return
                playing = self.play_stream(dict(song))

    def play_album(self, album_id, randomise):
        """
        Get the songs for the given album id and play them
        :param album_id:
        :param randomise:
        :return:
        """
        songs = self.get_album_tracks(album_id)

        if self.invert_random:
            randomise = not randomise

        if randomise:
            shuffle(songs)

        playing = True

        while playing:
            for song in songs:
                if not playing:
                    return
                playing = self.play_stream(dict(song))

    def play_playlist(self, playlist_id, randomise):
        """
        Get the tracks from the supplied playlist id and play them
        :param playlist_id:
        :param randomise:
        :return:
        """
        playlist_info = self.make_request(
            url='{}&id={}'.format(self.create_url('getPlaylist'), playlist_id)
        )
        songs = playlist_info['subsonic-response']['playlist']['entry']

        if self.invert_random:
            randomise = not randomise

        if randomise:
            shuffle(songs)

        playing = True

        while playing:
            for song in songs:
                if not playing:
                    return
                playing = self.play_stream(dict(song))

    def play_stream(self, track_data):
        """
        Given track data, generate the stream url and pass it to ffplay to handle.
        While stream is playing allow user input to control playback
        :param track_data: dict
        :return:
        """
        stream_url = self.create_url('download')
        song_id = track_data.get('id')

        if self.notify:
            self.notifications.get_cover_art(track_data)

        if not song_id:
            return False

        click.secho(
            '{} by {}'.format(
                track_data.get('title', ''),
                track_data.get('artist', '')
            ),
            fg='green'
        )

        self.scrobble(song_id)

        params = [
            'ffplay',
            '-i',
            '{}&id={}&format={}'.format(stream_url, song_id, self.format),
            '-showmode',
            '{}'.format(self.show_mode),
            '-window_title',
            '{} by {}'.format(
                track_data.get('title', ''),
                track_data.get('artist', '')
            ),
            '-autoexit',
            '-hide_banner',
            '-x',
            '500',
            '-y',
            '500',
            '-loglevel',
            'fatal',
            '-infbuf',
        ]

        params = self.pre_exe + params if len(self.pre_exe) > 0 else params
        
        if not self.display:
            params += ['-nodisp']

        try:
            if self.notify:
                self.notifications.show_notification(track_data)

            ffplay = Popen(params)

            has_finished = None
            open(os.path.join(click.get_app_dir('pSub'), 'play.lock'), 'w+').close()

            while has_finished is None:
                has_finished = ffplay.poll()
                if self.input_queue.empty():
                    time.sleep(1)
                    continue

                command = self.input_queue.get_nowait()
                self.input_queue.queue.clear()

                if 'x' in command.lower():
                    click.secho('Exiting!', fg='blue')
                    os.remove(os.path.join(click.get_app_dir('pSub'), 'play.lock'))
                    ffplay.terminate()
                    return False

                if 'b' in command.lower():
                    click.secho('Restarting Track....', fg='blue')
                    os.remove(os.path.join(click.get_app_dir('pSub'), 'play.lock'))
                    ffplay.terminate()
                    return self.play_stream(track_data)

                if 'n' in command.lower():
                    click.secho('Skipping...', fg='blue')
                    os.remove(os.path.join(click.get_app_dir('pSub'), 'play.lock'))
                    ffplay.terminate()
                    return True

            os.remove(os.path.join(click.get_app_dir('pSub'), 'play.lock'))
            return True

        except OSError as err:
            click.secho(
                f'Could not run ffplay. Please make sure it is installed, {str(err)}',
                fg='red'
            )
            click.launch('https://ffmpeg.org/download.html')
            return False
        except CalledProcessError as e:
            click.secho(
                'ffplay existed unexpectedly with the following error: {}'.format(e),
                fg='red'
            )
            return False

    def add_input(self):
        """
        This method runs in a separate thread (started in __init__).
        When the play.lock file exists it waits for user input and wrties it to a Queue.
        The play_stream method above deals with the user input when it occurs
        """
        while True:
            if not os.path.isfile(os.path.join(click.get_app_dir('pSub'), 'play.lock')):
                continue
            time.sleep(1)
            self.input_queue.put(click.prompt('', prompt_suffix=''))

    @staticmethod
    def show_banner(message):
        """
        Show a standardized banner with custom message and controls for playback
        :param message:
        """
        click.clear()
        click.echo('')
        click.secho('   {}   '.format(message), bg='blue', fg='black')
        click.echo('')
        click.secho('n = Next\nb = Beginning\nx = Exit', bg='yellow', fg='black')
        click.echo('')

    @staticmethod
    def set_default_config(config):
        """
        When no config file is detected, this method is run to write the default config
        :param config: path to config file
        """
        with open(config, 'w+') as config_file:
            config_file.write(
                """#
#          _________    ___.
#  ______ /   _____/__ _\_ |__
#  \____ \\\_____  \|  |  \ __ \
#  |  |_> >        \  |  / \_\ \\
#  |   __/_______  /____/|___  /
#  |__|          \/          \/
#
#

# This section defines the connection to your Subsonic server

server:
    # This is the url you would use to access your Subsonic server without the protocol
    # (http:// or https://)

    host: demo.subsonic.org

    # Username and Password next

    username: username
    password: password

    # If your Subsonic server is accessed over https:// set this to 'true'

    ssl: false

    # If you use a server with a specific API version set it here
    
    api: 

# This section defines the playback of music by pSub

streaming:

    # The default format is 'raw'
    # this means the original file is streamed from your server
    # and no transcoding takes place.
    # set this to mp3 or wav etc.
    # depending on the transcoders available to your user on the server

    format: raw

    # pSub utilises ffplay (https://ffmpeg.org/ffplay.html) to play the streamed media
    # by default the player window is hidden and control takes place through the cli
    # set this to true to enable the player window.
    # It allows for more controls (volume mainly) but will grab the focus of your
    # keyboard when tracks change which can be annoying if you are typing

    display: false

    # When the player window is shown, choose the default show mode
    # Options are:
    # 0: show video or album art
    # 1: show audio waves
    # 2: show audio frequency band using RDFT ((Inverse) Real Discrete Fourier Transform)

    show_mode: 0

    # Artist, Album and Playlist playback can accept a -r/--random flag.
    # by default, setting the flag on the command line means "randomise playback".
    # Setting the following to true will invert that behaviour so that playback is randomised by default
    # and passing the -r flag skips the random shuffle

    invert_random: false
    
    # pSub can use system notifications to alert you to a song change.
    # it will show you the details of the currently playing song.
    # to disable notification, set this to false
    
    notify: true

client:
    # Added extra client config for pre-exe commands, like using it in flatpak-spawn
    pre_exe: ''
"""
            )


# _________ .____    .___
# \_   ___ \|    |   |   |
# /    \  \/|    |   |   |
# \     \___|    |___|   |
#  \______  /_______ \___|
#         \/        \/
# Below are the CLI methods

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@click.group(
    invoke_without_command=True,
    context_settings=CONTEXT_SETTINGS
)
@click.option(
    '--config',
    '-c',
    is_flag=True,
    help='Edit the config file'
)
@click.option(
    '--test',
    '-t',
    is_flag=True,
    help='Test the server configuration'
)
@click.pass_context
def cli(ctx, config, test):
    if not os.path.exists(click.get_app_dir('pSub')):
        os.mkdir(click.get_app_dir('pSub'))

    config_file = os.path.join(click.get_app_dir('pSub'), 'config.yaml')

    if config:
        test = True

        try:
            click.edit(filename=config_file, extension='yaml')
        except UsageError:
            click.secho('pSub was unable to open your config file for editing.', bg='red', fg='black')
            click.secho('please open {} manually to edit your config file'.format(config_file), fg='yellow')
            return

    ctx.obj = pSub(config_file)

    if test:
        # Ping the server to check server config
        test_ok = ctx.obj.test_config()
        if not test_ok:
            return

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


pass_pSub = click.make_pass_decorator(pSub)


@cli.command(help='Play random tracks')
@click.option(
    '--music_folder',
    '-f',
    type=int,
    help='Specify the music folder to play random tracks from.',
)
@pass_pSub
def random(psub, music_folder):
    if not music_folder:
        music_folders = get_as_list(psub.get_music_folders()) + [{'name': 'All', 'id': None}]
        
        chosen_folder = questionary.select(
            "Choose a music folder to play random tracks from",
            choices=[folder.get('name') for folder in music_folders]
        ).ask()
        music_folder = next(folder.get('id') for folder in music_folders if folder.get('name') == chosen_folder)

    psub.show_banner('Playing Random Tracks')
    psub.play_random_songs(music_folder)


def get_as_list(list_inst: Union[List, Dict]) -> List[Dict]:
    if isinstance(list_inst,dict):
        list_inst = [list_inst]
    return list_inst


@cli.command(help='Play endless Radio based on a search')
@click.argument('search_term')
@pass_pSub
@click.pass_context
def radio(ctx, psub, search_term):
    results = get_as_list(psub.search(search_term).get('artist', []))

    if len(results) > 0:
        chosen_artist = questionary.select(
            "Choose an Artist to start a Radio play, or 'Search Again' to search again",
            choices=[artist.get('name') for artist in results] + ['Search Again']
        ).ask()
    else:
        click.secho('No Artists found matching {}'.format(search_term), fg='red', color=True)
        chosen_artist = 'Search Again'

    if chosen_artist == 'Search Again':
        search_term = questionary.text("Enter a new search term").ask()

        if not search_term:
            sys.exit(0)

        ctx.invoke(radio, search_term=search_term)
    else:
        radio_artist = next((art for art in results if art.get('name') == chosen_artist), None)

        if radio_artist is None:
            sys.exit(0)

        psub.show_banner('Playing Radio based on {}'.format(radio_artist.get('name')))
        psub.play_radio(radio_artist.get('id'))


@cli.command(help='Play songs from chosen Artist')
@click.argument('search_term')
@click.option(
    '--randomise',
    '-r',
    is_flag=True,
    help='Randomise the order of track playback',
)
@pass_pSub
@click.pass_context
def artist(ctx, psub, search_term, randomise):
    results = get_as_list(psub.search(search_term).get('artist', []))

    if len(results) > 0:
        chosen_artist = questionary.select(
            "Choose an Artist, or 'Search Again' to search again",
            choices=[artist.get('name') for artist in results] + ['Search Again']
        ).ask()
    else:
        click.secho('No artists found matching "{}"'.format(search_term), fg='red', color=True)
        chosen_artist = 'Search Again'

    if chosen_artist == 'Search Again':
        search_term = questionary.text("Enter a new search term").ask()

        if not search_term:
            sys.exit(0)

        ctx.invoke(artist, search_term=search_term, randomise=randomise)
    else:
        play_artist = next((art for art in results if art.get('name') == chosen_artist), None)

        if play_artist is None:
            sys.exit(0)

        psub.show_banner(
            'Playing {}tracks by {}'.format(
                'randomised ' if randomise else '',
                play_artist.get('name')
            )
        )
        psub.play_artist(play_artist.get('id'), randomise)


@cli.command(help='Play songs from chosen Album')
@click.argument('search_term')
@click.option(
    '--randomise',
    '-r',
    is_flag=True,
    help='Randomise the order of track playback',
)
@pass_pSub
@click.pass_context
def album(ctx, psub, search_term, randomise):
    results = get_as_list(psub.search(search_term).get('album', []))

    if len(results) > 0:
        chosen_album = questionary.select(
            "Choose an Album, or 'Search Again' to search again",
            choices=[album.get('name') for album in results] + ['Search Again']
        ).ask()
    else:
        click.secho('No albums found matching "{}"'.format(search_term), fg='red', color=True)
        chosen_album = 'Search Again'

    if chosen_album == 'Search Again':
        search_term = questionary.text("Enter a new search term").ask()

        if not search_term:
            sys.exit(0)

        ctx.invoke(album, search_term=search_term, randomise=randomise)
    else:
        play_album = next((alb for alb in results if alb.get('name') == chosen_album), None)

        if play_album is None:
            sys.exit(0)

        psub.show_banner(
            'Playing {}tracks from {} '.format(
                'randomised ' if randomise else '',
                play_album.get('name')
            )
        )
        psub.play_album(play_album.get('id'), randomise)


@cli.command(help='Play a chosen playlist')
@click.option(
    '--randomise',
    '-r',
    is_flag=True,
    help='Randomise the order of track playback',
)
@pass_pSub
def playlist(psub, randomise):
    playlists = get_as_list(psub.get_playlists())

    if len(playlists) > 0:
        chosen_playlist = questionary.select(
            "Choose a Playlist, or 'Search Again' to search again",
            choices=[plist.get('name') for plist in playlists] + ['Search Again']
        ).ask()
    else:
        click.secho('No playlists found', fg='red', color=True)
        sys.exit(0)

    play_list = next((plist for plist in playlists if plist.get('name') == chosen_playlist), None)

    if play_list is None:
        sys.exit(0)

    psub.show_banner(
        'Playing {} tracks from the "{}" playlist'.format(
            'randomised' if randomise else '',
            play_list.get('name')
        )
    )

    psub.play_playlist(play_list.get('id'), randomise)
