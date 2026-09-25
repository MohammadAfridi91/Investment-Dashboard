from core.ingestion.nse_universe import is_bfsi


def test_bfsi_exact_industry():
    assert is_bfsi("Banks", None)
    assert is_bfsi(None, "Life Insurance")


def test_bfsi_regex_on_industry():
    assert is_bfsi("Private Sector Bank", "Financial Services")
    assert is_bfsi("Housing Finance", None)


def test_bfsi_conglomerate_strict():
    assert is_bfsi("Finance", "Diversified")
    assert is_bfsi("Non Banking Financial Company (NBFC)", None)


def test_non_bfsi_technology():
    assert not is_bfsi("IT Services", "Information Technology")
    assert not is_bfsi("Pharmaceuticals", "Healthcare")
