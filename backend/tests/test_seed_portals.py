import pytest

from app.scripts.seed_portals import is_bare_ats_host


@pytest.mark.parametrize(
    "url",
    [
        "https://boards.greenhouse.io/",
        "https://boards.greenhouse.io",
        "https://job-boards.greenhouse.io/",
        "https://jobs.lever.co/",
        "https://jobs.eu.lever.co/",
        "https://jobs.ashbyhq.com/",
        "https://myworkdayjobs.com/",
        "https://wd1.myworkdaysite.com/",
        "https://www.jobs.lever.co/",
    ],
)
def test_bare_ats_host_detected(url):
    assert is_bare_ats_host(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://job-boards.greenhouse.io/anthropic",
        "https://boards.greenhouse.io/openai",
        "https://jobs.lever.co/acme",
        "https://www.4liberty.com/",
        "https://www.acciona.com/careers",
        "https://wd1.myworkdaysite.com/en-US/recruiting/acme/careers",
    ],
)
def test_real_company_urls_not_flagged_as_bare(url):
    assert is_bare_ats_host(url) is False
