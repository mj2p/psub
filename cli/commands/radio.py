import sys

import questionary
import rich_click as click

from cli.util import get_as_list, is_random, pass_pSub


@click.command()
@click.argument("search_term")
@pass_pSub
@click.pass_context
def radio(ctx, psub, search_term):
    """
    Play endless Radio based on a search
    """
    results = get_as_list(psub.search(search_term).get("artist", []))

    if len(results) > 0:
        chosen_artist = questionary.select(
            "Choose an Artist to start a Radio play, or 'Search Again' to search again",
            choices=[artist.get("name") for artist in results] + ["Search Again"],
        ).ask()
    else:
        click.secho(
            "No artists found matching {}".format(search_term), fg="red", color=True
        )
        chosen_artist = "Search Again"

    if chosen_artist == "Search Again":
        search_term = questionary.text("Enter a new search term").ask()

        if search_term is None:
            return

        ctx.invoke(radio, search_term=search_term)
        return

    radio_artist = next(
        (art for art in results if art.get("name") == chosen_artist), None
    )

    if radio_artist is None:
        raise click.ClickException("Unable to retrieve radio information")

    psub.show_banner(f"Playing Radio based on {radio_artist.get('name', '')}")
    psub.play_radio(radio_artist.get("id"))
