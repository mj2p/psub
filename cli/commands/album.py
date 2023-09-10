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
def album(ctx, psub, search_term, randomise):
    """
    Play songs from chosen Album
    """
    results = get_as_list(psub.search(search_term).get("album", []))

    if len(results) > 0:
        chosen_album = questionary.select(
            "Choose an Album, or 'Search Again' to search again",
            choices=[alb.get("name") for alb in results] + ["Search Again"],
        ).ask()
    else:
        click.secho(
            'No albums found matching "{}"'.format(search_term), fg="red", color=True
        )
        chosen_album = "Search Again"

    if chosen_album == "Search Again":
        search_term = questionary.text("Enter a new search term").ask()

        if search_term is None:
            return

        ctx.invoke(album, search_term=search_term, randomise=randomise)
        return

    play_album = next((alb for alb in results if alb.get("name") == chosen_album), None)

    if play_album is None:
        raise click.ClickException("Unable to retrieve album information")

    psub.show_banner(
        f"Playing {play_album.get('name', '')} by {play_album.get('artist', '')} {is_random(psub, randomise)}"
    )
    psub.play_album(play_album.get("id"), randomise)
