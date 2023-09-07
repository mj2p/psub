import time
from subprocess import CalledProcessError, Popen, run
from typing import Dict

import rich_click as click

from players.base_player import PsubPlayer


class Ffplay(PsubPlayer):
    """
    FFPlay player.
    Requires ffplay binary to be installed on the system
    https://ffmpeg.org/ffplay.html
    """

    def __init__(self, player_config: Dict):
        super().__init__(player_config)
        self.display = player_config.get("display", False)
        self.show_mode = player_config.get("show_mode", 0)
        self.pre_exe = player_config.get("pre_exe", "")
        self.parse_pre_exe()

    def parse_pre_exe(self) -> None:
        self.pre_exe = self.pre_exe.split(" ") if self.pre_exe != "" else []

    def play(self, track_data: Dict):
        super().play(track_data)
        self.track_data = track_data

        params = [
            "ffplay",
            "-i",
            track_data["stream_url"],
            "-showmode",
            f"{self.show_mode}",
            "-window_title",
            f"{track_data.get('title', '')} by {track_data.get('artist', '')}",
            "-autoexit",
            "-hide_banner",
            "-x",
            "500",
            "-y",
            "500",
            "-loglevel",
            "fatal",
            "-infbuf",
        ]

        params = self.pre_exe + params if len(self.pre_exe) > 0 else params

        if not self.display:
            params += ["-nodisp"]

        try:
            self.stream = Popen(params)

        except OSError as err:
            raise click.ClickException(
                "Could not run ffplay.\n"
                f"Please make sure it is installed,\n"
                "https://ffmpeg.org/download.html\n\n"
                f"{str(err)}",
            )
        except CalledProcessError as e:
            raise click.ClickException(
                f"ffplay exited unexpectedly with the following error: {e}",
            )

    def is_playing(self):
        if self.stream.poll() is None:
            return True
        else:
            time.sleep(2)
            return False

    def stop(self):
        super().stop()
        self.stream.terminate()
