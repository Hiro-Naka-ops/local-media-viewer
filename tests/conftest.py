import pytest

import local_media_viewer.app as app_module
from local_media_viewer import i18n


@pytest.fixture(autouse=True)
def japanese_ui(monkeypatch):
    """Pin the UI to Japanese whatever Windows is set to.

    The tests check labels by their Japanese wording, and a fresh settings file
    follows the system language, so without this they would pass or fail with
    the machine they run on. A test that switches language is also undone here.
    """
    monkeypatch.setattr(app_module, "system_language", lambda: "ja_JP")
    i18n.set_language(i18n.JAPANESE)
    yield
    i18n.set_language(i18n.JAPANESE)
