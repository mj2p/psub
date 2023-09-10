import os
from typing import Dict, List

import rich_click as click
from rich import print


class PsubPlayer(object):
    def __init__(self, player_config: Dict):
        self.config = player_config
        self.stream = None
        self.track_data = None
        self.playlist = []

    def load_playlist(self, playlist: List[str]):  # pragma: no cover
        pass

    def next(self):  # pragma: no cover
        pass

    def previous(self):  # pragma: no cover
        pass

    def play(self, track_data: Dict):
        print(
            f"\n:play_button: [green]{track_data.get('title', '')} by {track_data.get('artist', '')}[/]"
        )
        click.echo("\r", nl=False)
        open(os.path.join(click.get_app_dir("pSub"), "play.lock"), "w+").close()

    @staticmethod
    def clear_lock():
        os.remove(os.path.join(click.get_app_dir("pSub"), "play.lock"))

    def is_playing(self):  # pragma: no cover
        pass

    def stop(self):
        self.clear_lock()
