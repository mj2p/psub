import hashlib
import os
import string
import sys
import time
import sys
from datetime import timedelta
from random import SystemRandom, shuffle
from subprocess import CalledProcessError, Popen, call
from threading import Thread

import requests
from click import UsageError

try:
    from queue import LifoQueue
except ImportError:
    from Queue import LifoQueue  # noqa

import click
import yaml


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
        self.ssl = server_config.get('ssl', False)

        # get the streaming config
        streaming_config = config.get('streaming', {})
        self.format = streaming_config.get('format', 'raw')
        self.invert_random = streaming_config.get('invert_random', False)
        self.cover_art = streaming_config.get('cover_art', False)

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
        salt = ''.join(SystemRandom().choice(characters) for i in range(9))
        salted_password = self.password + salt
        token = hashlib.md5(salted_password.encode('utf-8')).hexdigest()
        return token, salt

    def create_url(self, endpoint):
        """
        build the standard url for interfacing with the Subsonic REST API
        :param endpoint: REST endpoint to incorporate in the url
        """
        token, salt = self.hash_password()
        url = '{}://{}/rest/{}?u={}&t={}&s={}&v=1.16.0&c=pSub&f=json'.format(
            'https' if self.ssl else 'http',
            self.host,
            endpoint,
            self.username,
            token,
            salt
        )
        return url

    @staticmethod
    def make_request(url):
        """
        GET the supplied url and resturn the response as json.
        Handle any errors present.
        :param url: full url. see create_url method for details
        :return: Subsonic response or None on failure
        """
        try:
            r = requests.get(url=url)
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

    def search(self, query, search_version='3'):
        """
        search using query and return the result
        :return:
        :param query: search term string
        """
        results = self.make_request(
            url='{}&query={}&albumCount=1000'.format(self.create_url('search{}'.format(
                search_version)), query)
        )
        if results:
            return results['subsonic-response']['searchResult{}'.format(search_version)]
        return []

    def get_artists(self):
        """
        Gather list of Artists from the Subsonic server
        :return: list
        """
        artists = self.make_request(url=self.create_url('getArtists'))
        if artists:
            return artists['subsonic-response']['artists']['index']
        return []

    def get_playlists(self):
        """
        Get a list of available playlists from the server
        :return:
        """
        playlists = self.make_request(url=self.create_url('getPlaylists'))
        if playlists:
            return playlists['subsonic-response']['playlists']['playlist']
        return []

    def get_music_folders(self):
        """
        Gather list of Music Folders from the Subsonic server
        :return: list
        """
        music_folders = self.make_request(url=self.create_url('getMusicFolders'))
        if music_folders:
            return music_folders['subsonic-response']['musicFolders']['musicFolder']
        return []

    def get_album_tracks(self, album_id):
        """
        return a list of album track ids for the given album id
        :param album_id: id of the album
        :return: list
        """
        album_info = self.make_request('{}&id={}'.format(self.create_url('getAlbum'), album_id))
        songs = []

        for song in album_info['subsonic-response']['album']['song']:
            songs.append(song)

        return songs

    def play_random_songs(self, music_folder, banner):
        """
        Gather random tracks from the Subsonic server and playthem endlessly
        :param music_folder: integer denoting music folder to filter tracks
        """
        url = self.create_url('getRandomSongs')

        if music_folder != 0:
            url = '{}&musicFolderId={}'.format(url, music_folder)

        playing = True

        width = None

        while playing:
            random_songs = self.make_request(url)

            if not random_songs:
                return

            songs = []

            for random_song in random_songs['subsonic-response']['randomSongs']['song']:
                songs.append(random_song)

            for song in songs:
                if not playing:
                    return
                width = self.draw_player(banner, songs, song, width)
                playing = self.play_stream(dict(song))

    def play_radio(self, radio_id, banner):
        """
        Get songs similar to the supplied id and play them endlessly
        :param radio_id: id of Artist
        """
        playing = True

        width = None

        while playing:
            similar_songs = self.make_request(
                '{}&id={}'.format(self.create_url('getSimilarSongs2'), radio_id)
            )

            if not similar_songs:
                return

            songs = []

            for radio_track in similar_songs['subsonic-response']['similarSongs2']['song']:
                songs.append(radio_track)

            for song in songs:
                if not playing:
                    return
                width = self.draw_player(banner, songs, song, width)
                playing = self.play_stream(dict(song))

    def play_artist(self, artist_id, randomise, banner):
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

        width = None

        while playing:
            for song in songs:
                if not playing:
                    return
                width = self.draw_player(banner, songs, song, width)
                playing = self.play_stream(dict(song))

    def play_album(self, album_id, randomise, banner):
        """
        Get the songs for the given album id and play them
        :param album_id:
        :param randomise:
        :param banner:
        :return:
        """

        songs = self.get_album_tracks(album_id)

        if self.invert_random:
            randomise = not randomise

        if randomise:
            shuffle(songs)

        width = None

        for song in songs:
            width = self.draw_player(banner, songs, song, width)
            self.play_stream(dict(song))

    def play_playlist(self, playlist_id, randomise, banner):
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

        width = None

        while playing:
            for song in songs:
                if not playing:
                    return
                width = self.draw_player(banner, songs, song, width)
                playing = self.play_stream(dict(song))

    def play_stream(self, track_data):
        """
        Given track data, generate the stream url and pass it to mpv to handle.
        While stream is playing allow user input to control playback
        :param track_data: dict
        :return:
        """
        stream_url = self.create_url('stream')
        song_id = track_data.get('id')

        if not song_id:
            return False

        self.scrobble(song_id)

        params = [
            'mpv',
            '--no-audio-display',
            '--really-quiet',
            '{}&id={}&format={}'.format(stream_url, song_id, self.format)
        ]

        try:
            mpv = Popen(params, shell=False, universal_newlines=True)

            has_finished = None

            while has_finished is None:
                has_finished = mpv.poll()
                time.sleep(.01)

            return True

        except OSError:
            click.secho(
                'Could not run mpv. Please make sure it is installed',
                fg='red'
            )
            click.launch('https://ffmpeg.org/download.html')
            return False
        except CalledProcessError as e:
            click.secho(
                'mpv existed unexpectedly with the following error: {}'.format(e),
                fg='red'
            )
            return False

    def show_cover_art(self, album_id):
        """
        Render the album cover art in the terminal. Needs kitty terminal.
        :param album_id: int
        """
        url = '{}&id=al-{}&size=500'.format(self.create_url('getCoverArt'), album_id)
        call('curl -s "{}" | kitty +kitten icat --align center'.format(url), shell=True)
        click.echo('')

    def draw_player(self, banner, songs, current_song, old_width):
        """
        Give banner message, track data and current track and draw a pretty player with album art
        :param banner: str
        :param songs: dict
        :param current_song: dict
        :return:
        """
        # Set the winow title
        sys.stdout.write('\x1b]2;{} - {} - pSub\x07'.format(
            current_song['title'],
            current_song['artist']
        ))

        width = int(os.get_terminal_size().columns)

        offset = ' ' * int(width / 6)
        line_limit = width - len(offset)

        if width != old_width:
            click.clear()

        self.show_banner(banner, width)

        if self.cover_art and 'kitty' in os.environ.get('TERM', ''):
            self.show_cover_art(current_song['albumId'])

        click.secho('{}Tracklist:'.format(offset), fg='yellow')
        click.echo('')

        for song in songs:
            # Highlight the current track
            if song['id'] == current_song['id']:
                click.secho(
                    '{}    {} by {}'.format(
                        offset,
                        dict(song).get('title', ''),
                        dict(song).get('artist', '')
                    )[0:line_limit],
                    fg='cyan'
                )
            else:
                click.secho(
                    '{}    {} by {}'.format(
                        offset,
                        dict(song).get('title', ''),
                        dict(song).get('artist', '')
                    )[0:line_limit],
                    fg='green'
                )

        click.echo('')

        click.secho(
            '{}Current track: {} | {} | {} | {} '.format(
                offset,
                str(timedelta(seconds=dict(current_song).get('duration', 0))),
                dict(current_song).get('year', ''),
                str(dict(current_song).get('bitRate', '')) + 'kbps',
                dict(current_song).get('suffix', '')
            )[0:line_limit],
            fg='cyan',
            nl=False
        )
        return width

    @staticmethod
    def show_banner(message, width):
        """
        Show a standardized banner with custom message and controls for playback
        :param message:
        """
        offset = ' ' * int(width / 6)
        # Move the cursor to the top of the screen
        print('\033[;H')
        # click.echo('        ', nl=False)
        banner = click.style('   {}   '.format(message), bg='blue', fg='black')
        click.echo('{}{}'.format(offset, banner))
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


# This section defines the playback of music by pSub

streaming:

    # The default format is 'raw'
    # this means the original file is streamed from your server
    # and no transcoding takes place.
    # set this to mp3 or wav etc.
    # depending on the transcoders available to your user on the server

    format: raw

    # Artist, Album and Playlist playback can accept a -r/--random flag.
    # by default, setting the flag on the command line means "randomise playback".
    # Setting the following to true will invert that behaviour so that playback is randomised by default
    # and passing the -r flag skips the random shuffle

    invert_random: false

    # If you are using kitty terminal, you can have pSub display album cover art

    cover_art: true
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
@click.pass_context
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
        music_folders = [{'name': 'All', 'id': 0}] + psub.get_music_folders()
        click.secho(
            '\n'.join(
                '{}\t{}'.format(folder['id'], folder['name']) for folder in music_folders
            ),
            fg='yellow'
        )
        music_folder = click.prompt(
            'Choose a music folder from the options above',
            default=0
        )

    banner = 'Playing Random Tracks'

    psub.play_random_songs(music_folder, banner)


@cli.command(help='Play endless Radio based on a search')
@click.argument('search_term')
@pass_pSub
def radio(psub, search_term):
    radio_id = None

    while not radio_id:
        results = psub.search(search_term)
        click.secho('Artists', bg='red', fg='black')
        click.secho(
            '\n'.join(
                '{}\t{}'.format(
                    str(artist.get('id')).ljust(7),
                    str(artist.get('name')).ljust(30),
                ) for artist in results.get('artist', [])
            ),
            fg='yellow'
        )

        radio_id = click.prompt(
            'Enter an id to start radio or Enter to search again',
            type=int,
            default=0,
            show_default=False
        )

        if not radio_id:
            search_term = click.prompt('Enter a new search')

    banner = 'Playing Radio'

    psub.play_radio(radio_id, banner)


@cli.command(help='Play songs from chosen Artist')
@click.argument('search_term')
@click.option(
    '--randomise',
    '-r',
    is_flag=True,
    help='Randomise the order of track playback',
)
@pass_pSub
def artist(psub, search_term, randomise):
    artist_id = None
    results = {}

    while not artist_id:
        results = psub.search(search_term)
        click.secho('Artists', bg='red', fg='black')
        click.secho(
            '\n'.join(
                '{}\t{}'.format(
                    str(artist.get('id')).ljust(7),
                    str(artist.get('name')).ljust(30),
                ) for artist in results.get('artist', [])
            ),
            fg='yellow'
        )

        artist_id = click.prompt(
            'Enter an id to start or Enter to search again',
            default=0,
            type=int,
            show_default=False
        )

        if not artist_id:
            search_term = click.prompt('Enter an artist name to search again')

    banner = 'Playing {} tracks by {}'.format(
        'randomised' if randomise else '',
        ''.join(
            artist.get('name') for artist in results.get('artist', []) if int(artist.get('id')) == int(artist_id)
        )
    )

    psub.play_artist(artist_id, randomise, banner)


@cli.command(help='Play songs from chosen Album')
@click.argument('search_term')
@click.option(
    '--randomise',
    '-r',
    is_flag=True,
    help='Randomise the order of track playback',
)
@pass_pSub
def album(psub, search_term, randomise):
    album_id = None
    results = []

    while not album_id:
        results = sorted(
                # For some reason we get better results with `search2` over `search3`
                psub.search(search_term, '2')['album'],
                key=lambda k: k['year']
        )
        click.secho('Albums', bg='red', fg='black')
        click.secho(
            '\n'.join(
                '{}\t{}\t{} ({})'.format(
                    str(album.get('id')).ljust(7),
                    str(album.get('artist')).ljust(30),
                    album.get('album'),
                    str(album.get('year'))
                ) for album in results
            ),
            fg='yellow'
        )

        album_id = click.prompt(
            'Enter an id to start or Enter to search again',
            type=int,
            default=0,
            show_default=False
        )

        if not album_id:
            search_term = click.prompt('Enter an album name to search again')

    banner = 'Playing {} tracks from {}'.format(
                'randomised' if randomise else '',
                ''.join(
                    album.get('album') for album in results.get('album', []) if int(album.get('id')) == int(album_id)
                )
            )

    psub.play_album(album_id, randomise, banner)


@cli.command(help='Play a chosen playlist')
@click.option(
    '--randomise',
    '-r',
    is_flag=True,
    help='Randomise the order of track playback',
)
@pass_pSub
def playlist(psub, randomise):
    playlist_id = None

    while not playlist_id:
        playlists = psub.get_playlists()
        click.secho('Playlists', bg='red', fg='black')
        click.secho(
            '\n'.join(
                '{}\t{}\t{} tracks'.format(
                    str(playlist.get('id')).ljust(7),
                    str(playlist.get('name')).ljust(30),
                    playlist.get('songCount')
                ) for playlist in playlists
            ),
            fg='yellow'
        )

        playlist_id = click.prompt(
            'Enter an id to start',
            type=int,
        )

    banner = 'Playing {} tracks from the "{}" playlist'.format(
        'randomised' if randomise else '',
        ''.join(
            playlist.get('name') for playlist in playlists if int(playlist.get('id')) == int(playlist_id)
        )
    )

    psub.play_playlist(playlist_id, randomise, banner)
