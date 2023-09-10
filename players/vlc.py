import time
from typing import Dict

import vlc
from wurlitzer import (  # vlc raises console errors from C code. This gets rid of most of them in the CLI output
    pipes,
)

from players.base_player import PsubPlayer


class Vlc(PsubPlayer):
    """
    VLC Player.
    Requires VLC to be installed on the system
    """

    def __init__(self, player_config: Dict):
        super().__init__(player_config)
        self.playing_interval = player_config.get("playing_interval", 2)
        self.player = None

        with pipes() as (_, _):
            self.instance = vlc.Instance()

    def play(self, track_data: Dict):
        super().play(track_data)

        with pipes() as (_, _):
            self.player = self.instance.media_player_new(track_data["stream_url"])
            can_play = self.player.play()  # returns 0 on success or -1 on error

            if can_play > -1:
                time.sleep(
                    self.playing_interval
                )  # takes a moment for is_playing() to return correctly

    def is_playing(self):
        with pipes() as (_, _):
            return self.player.is_playing()

    def stop(self):
        super().stop()

        with pipes() as (_, _):
            self.player.stop()
