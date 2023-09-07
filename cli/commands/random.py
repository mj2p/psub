import questionary
import rich_click as click

from cli.util import get_as_list, pass_pSub


@click.command()
@click.option(
    "--music_folder",
    "-f",
    type=int,
    help="Specify the music folder to play random tracks from.",
)
@pass_pSub
def random(psub, music_folder):
    """
    Play random tracks
    """
    if not music_folder:
        music_folders = get_as_list(psub.get_music_folders()) + [
            {"name": "All", "id": None}
        ]

        chosen_folder = questionary.select(
            "Choose a music folder to play random tracks from",
            choices=[folder.get("name") for folder in music_folders],
        ).ask()

        music_folder = next(
            folder.get("id")
            for folder in music_folders
            if folder.get("name") == chosen_folder
        )

        if music_folder is None:
            raise click.ClickException("Unable to retrieve music folder information")

    psub.show_banner("Playing Random Tracks")
    psub.play_random_songs(music_folder)
