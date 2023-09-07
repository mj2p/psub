import questionary
import rich_click as click

from cli.util import get_as_list, is_random, pass_pSub


@click.command()
@click.argument("search_term")
@click.option(
    "--randomise",
    "-r",
    is_flag=True,
    help="Randomise the order of track playback",
)
@pass_pSub
@click.pass_context
def artist(ctx, psub, search_term, randomise):
    """
    Play songs from chosen Artist
    """
    results = get_as_list(psub.search(search_term).get("artist", []))

    if len(results) > 0:
        chosen_artist = questionary.select(
            "Choose an Artist, or 'Search Again' to search again",
            choices=[art.get("name") for art in results] + ["Search Again"],
        ).ask()
    else:
        click.secho(
            'No artists found matching "{}"'.format(search_term), fg="red", color=True
        )
        chosen_artist = "Search Again"

    if chosen_artist == "Search Again":
        search_term = questionary.text("Enter a new search term").ask()

        if search_term is None:
            return

        ctx.invoke(artist, search_term=search_term, randomise=randomise)
        return

    play_artist = next(
        (art for art in results if art.get("name") == chosen_artist), None
    )

    if play_artist is None:
        raise click.ClickException("Unable to retrieve artist information")

    psub.show_banner(
        f"Playing tracks by {play_artist.get('name', '')} {is_random(psub, randomise)}"
    )
    psub.play_artist(play_artist.get("id"), randomise)
