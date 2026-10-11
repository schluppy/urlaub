"""Gemeinsame Testhilfen."""
from konten.models import Familie


def fam(name="Muster", bundesland="SH"):
    """Testfamilie – derselbe Name wie bei `beispieldaten`."""
    return Familie.objects.get_or_create(name=name, defaults={"bundesland": bundesland})[0]
