import hashlib
import os
import string
import time
from random import SystemRandom
from subprocess import CalledProcessError, Popen
from threading import Thread

import requests
import sys

try:
    from queue import LifoQueue
except ImportError:
    from Queue import LifoQueue

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
        self.display = streaming_config.get('display', False)
        self.show_mode = streaming_config.get('show_mode', 0)

        # Ping the server to check server config
        self.test_config()

        # use a Queue to handle command input while a file is playing.
        # set the thread going now
        self.input_queue = LifoQueue()
        input_thread = Thread(target=self.add_input)
        input_thread.daemon = True
        input_thread.start()

        # remove the lock file if one exists
        if os.path.isfile(os.path.join(click.get_app_dir('pSub'), 'play.lock')):
            os.remove(os.path.join(click.get_app_dir('pSub'), 'play.lock'))

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
        else:
            click.secho('Test Failed! Please check your config', fg='black', bg='red')
            click.edit(filename=os.path.join(click.get_app_dir('pSub'), 'config.yaml'))

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
        url = '{}://{}/rest/{}?u={}&t={}&s={}&v=1.15.0&c=pSub&f=json'.format(
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
        r = requests.get(url=url)

        try:
            response = r.json()
        except ValueError:
            response = {
                'subsonic-response': {
                    'error': {
                        'code': 100,
                        'message': r.text
                    },
                    'version': '1.15.0',
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

    def search(self, query):
        """
        search using query and return the result
        :return:
        :param query: search term string
        """
        results = self.make_request(
            url='{}&query={}'.format(self.create_url('search2'), query)
        )
        if results:
            return results['subsonic-response']['searchResult2']
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

    def get_music_folders(self):
        """
        Gather list of Music Folders from the Subsonic server
        :return: list
        """
        music_folders = self.make_request(url=self.create_url('getMusicFolders'))
        if music_folders:
            return music_folders['subsonic-response']['musicFolders']['musicFolder']
        return []

    def play_random_songs(self, music_folder):
        """
        Gather random tracks from the Subsonic server and playthem endlessly
        :param music_folder: integer denoting music folder to filter tracks
        """
        url = self.create_url('getRandomSongs')

        if music_folder != 0:
            url = '{}&musicFolderId={}'.format(url, music_folder)

        playing = True

        while playing:
            random_songs = self.make_request(url)

            if not random_songs:
                return

            for random_song in random_songs['subsonic-response']['randomSongs']['song']:
                if not playing:
                    return
                playing = self.play_stream(dict(random_song))

    def play_radio(self, radio_id):
        """
        Get songs similar to the suplpied id and play them endlessly
        :param radio_id: id of Album Artist or Song
        """
        playing = True
        while playing:
            similar_songs = self.make_request(
                '{}&id={}'.format(self.create_url('getSimilarSongs'), radio_id)
            )

            if not similar_songs:
                return

            for radio_track in similar_songs['subsonic-response']['similarSongs']['song']:
                if not playing:
                    return
                playing = self.play_stream(dict(radio_track))

    def play_stream(self, track_data):
        """
        Given track data, generate the stream url and pass it to ffplay to handle.
        While stream is playing allow user input to control playback
        :param track_data: dict
        :return:
        """
        stream_url = self.create_url('download')
        song_id = track_data.get('id')

        if not song_id:
            return False

        click.secho(
            '{} by {}'.format(
                track_data.get('title', ''),
                track_data.get('artist', '')
            ),
            fg='green'
        )

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
        ]

        if not self.display:
            params += ['-nodisp']

        try:
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

                if command == 'x':
                    click.secho('Exiting!', fg='blue')
                    os.remove(os.path.join(click.get_app_dir('pSub'), 'play.lock'))
                    ffplay.terminate()
                    return False

                if command == 'n':
                    click.secho('Skipping...', fg='blue')
                    os.remove(os.path.join(click.get_app_dir('pSub'), 'play.lock'))
                    ffplay.terminate()
                    return True

            os.remove(os.path.join(click.get_app_dir('pSub'), 'play.lock'))
            return True

        except OSError:
            click.secho(
                'Could not run ffplay. Please make sure it is installed',
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
        click.secho('n = Next\nx = Exit', bg='yellow', fg='black')
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

    # pSub utilises ffplay (https://ffmpeg.org/ffplay.html) to play the streamed media
    # by default the player window is hidden and control takes place through the cli
    # set this to true to enable the player window. 
    # It allows for more controls but will grab the focus of your 
    # keyboard when tracks change which can be annoying if you are typing 

    display: false

    # When the player window is shown, choose the default show mode
    # Options are:
    # 0: show video or album art
    # 1: show audio waves
    # 2: show audio frequency band using RDFT ((Inverse) Real Discrete Fourier Transform)

    show_mode: 0
                
"""
            )


# _________ .____    .___
# \_   ___ \|    |   |   |
# /    \  \/|    |   |   |
# \     \___|    |___|   |
#  \______  /_______ \___|
#         \/        \/
# Below are the CLI methods

@click.group()
@click.pass_context
def cli(ctx):
    if not os.path.exists(click.get_app_dir('pSub')):
        os.mkdir(click.get_app_dir('pSub'))

    config = os.path.join(click.get_app_dir('pSub'), 'config.yaml')

    ctx.obj = pSub(config)


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

    psub.show_banner('Playing Random Tracks')
    psub.play_random_songs(music_folder)


@cli.command(help='play radio based on a search')
@click.argument('target')
@pass_pSub
def radio(psub, target):
    radio_id = None

    while not radio_id:
        results = psub.search(target)
        click.secho('Songs', bg='red', fg='black')
        click.secho(
            '\n'.join(
                '{}\t{}\t{}'.format(
                    song.get('id'),
                    song.get('artist'),
                    song.get('title')
                ) for song in results.get('song', [])
            ),
            fg='yellow'
        )
        click.secho('Albums', bg='red', fg='black')
        click.secho(
            '\n'.join(
                '{}\t{}\t{}'.format(
                    album.get('id'),
                    album.get('artist'),
                    album.get('title')
                ) for album in results.get('album', [])
            ),
            fg='yellow'
        )
        click.secho('Artists', bg='red', fg='black')
        click.secho(
            '\n'.join(
                '{}\t{}'.format(
                    artist.get('id'),
                    artist.get('name'),
                ) for artist in results.get('artist', [])
            ),
            fg='yellow'
        )

        radio_id = click.prompt(
            'Enter an id to start radio or Enter to search again',
            default='',
            show_default=False
        )

        if not radio_id:
            target = click.prompt('Enter a new search target')

    psub.show_banner('Playing Radio')

    psub.play_radio(radio_id)


@cli.command()
def config():
    click.edit(filename=os.path.join(click.get_app_dir('pSub'), 'config.yaml'))
