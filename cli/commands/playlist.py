import sys

import questionary
import rich_click as click

from cli.util import get_as_list, is_random, pass_pSub


@click.command()
@click.option(
    "--randomise",
    "-r",
    is_flag=True,
    help="Randomise the order of track playback",
)
@pass_pSub
def playlist(psub, randomise):
    """
    Play a chosen playlist
    """
    playlists = get_as_list(psub.get_playlists())

    if len(playlists) > 0:
        chosen_playlist = questionary.select(
            "Choose a Playlist, or 'Search Again' to search again",
            choices=[plist.get("name") for plist in playlists] + ["Search Again"],
        ).ask()
    else:
        raise click.ClickException("No playlists found")

    play_list = next(
        (plist for plist in playlists if plist.get("name") == chosen_playlist), None
    )

    if play_list is None:
        raise click.ClickException("Unable to retrieve playlist information")

    psub.show_banner(
        f"Playing the {play_list.get('name', '')} playlist {is_random(psub, randomise)}"
    )
    psub.play_playlist(play_list.get("id"), randomise)
