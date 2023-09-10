# _________ .____    .___
# \_   ___ \|    |   |   |
# /    \  \/|    |   |   |
# \     \___|    |___|   |
#  \______  /_______ \___|
#         \/        \/

import os

import rich_click as click

from cli.commands.album import album
from cli.commands.artist import artist
from cli.commands.playlist import playlist
from cli.commands.radio import radio
from cli.commands.random import random
from client.psub import PsubClient

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group(invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
@click.option("--config", "-c", is_flag=True, help="Edit the config file")
@click.option("--test", "-t", is_flag=True, help="Test the server connection")
@click.pass_context
def psub(ctx, config, test):
    if not os.path.exists(click.get_app_dir("pSub")):
        os.mkdir(click.get_app_dir("pSub"))

    config_file_path = os.path.join(click.get_app_dir("pSub"), "config.yaml")

    # TODO: migrate to new config file

    if config:
        test = True

        try:
            click.edit(filename=config_file_path, extension="yaml")
        except click.UsageError:
            raise click.ClickException(
                "pSub was unable to open your config file for editing.\n"
                f"Please open {config_file_path} manually to edit your config file"
            )

    ctx.obj = PsubClient(config_file_path)

    if test:
        # Ping the server to check server config
        ctx.obj.test_config()

    if ctx.invoked_subcommand is None and not (test or config):
        click.echo(ctx.get_help())


psub.add_command(album)
psub.add_command(artist)
psub.add_command(playlist)
psub.add_command(radio)
psub.add_command(random)
