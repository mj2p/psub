import rich_click as click
from pynotifier import Notification, NotificationClient
from pynotifier.backends import platform


class Notifications(object):
    def __init__(self):
        self.client = NotificationClient()
        self.client.register_backend(platform.Backend())

    def show_notification(self, track_data):
        try:
            notification = Notification(
                title=track_data.get("title", "No Title"),
                description=track_data.get("artist", "No Artist"),
                icon_path="/tmp/art.jpg",
                duration=5,
                urgency="normal",
                app_name="pSub",
            )
        except ValueError:
            return
        except SystemError as e:
            raise click.ClickException(
                f"There was an error creating a notification:\n\n{e}"
            )

        try:
            self.client.notify_all(notification)
        except (ImportError, SystemError) as e:
            raise click.ClickException(
                f"There was an error sending a notification:\n\n{e}"
            )
