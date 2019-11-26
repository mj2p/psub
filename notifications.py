import gi
import requests
gi.require_version('Notify', '0.7')
from gi.repository import Notify, GdkPixbuf


class Notifications(object):
    def __init__(self, psub):
        Notify.init("pSub")
        self.psub = psub

    def get_cover_art(self, track_data):
        cover_url = self.psub.create_url('getCoverArt')
        if track_data.get('coverArt') is not None:
            r = requests.get(
                '{}&id={}&size=128'.format(cover_url, track_data.get('coverArt')),
                verify=self.psub.verify_ssl
            )
            cover = r.content
        else:
            c = open('no_cover.jpg', 'rb')
            cover = c.read()

        open('/tmp/art.jpg', 'wb').write(cover)

    @staticmethod
    def show_notification(track_data):
        GdkPixbuf.Pixbuf.new_from_file('/tmp/art.jpg')
        notification = Notify.Notification.new(track_data.get('artist'), track_data.get('title'))
        cover_art = GdkPixbuf.Pixbuf.new_from_file("/tmp/art.jpg")
        notification.set_image_from_pixbuf(cover_art)
        notification.show()
