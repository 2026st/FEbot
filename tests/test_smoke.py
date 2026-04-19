"""Installability and import sanity checks (no Slack / API required)."""


def test_package_exports_version() -> None:
    import febot

    assert febot.__version__
