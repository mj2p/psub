from threading import Thread
from typing import Dict, List

import mpv

from players.base_player import PsubPlayer


class Mpv(PsubPlayer):
    """
    MPV Player
    Requires libmpv to be installed on the system
    """

    def __init__(self, player_config: Dict):
        super().__init__(player_config)
        self.player = None
        self.playing = False

    def load_playlist(self, playlist: List[Dict]):
        for track_data in playlist:
            self.player.playlist_append(track_data["stream_url"])

    def play(self, track_data: Dict):
        super().play(track_data)
        self.player = mpv.MPV()
        self.player.play(track_data["stream_url"])
        self.playing = True
        Thread(target=self.wait_for_play).start()

    def wait_for_play(self):
        self.player.wait_for_playback()
        self.playing = False

    def is_playing(self):
        return self.playing

    def stop(self):
        super().stop()
        self.player.terminate()
        self.playing = False
