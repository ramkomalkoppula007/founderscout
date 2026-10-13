from founderscout.sources import domain_of, looks_relevant, pick_homepage
from founderscout.sources.hn import clean_html, posts_from_file
from founderscout.sources.yc import post_from_company

from .conftest import FIXTURES


def test_clean_html_returns_text_and_links():
    text, urls = clean_html('Acme | Remote<p>We&#x27;re hiring. '
                            '<a href="https:&#x2F;&#x2F;acme.example&#x2F;jobs">jobs</a>')
    assert text == "Acme | Remote\n\nWe're hiring. jobs"
    assert urls == ["https://acme.example/jobs"]


def test_file_source_keeps_only_top_level_posts():
    posts = posts_from_file(FIXTURES / "hn_posts.json")
    assert [post.source_id for post in posts] == ["1001", "1002", "1003", "1005"]
    assert posts[0].text.startswith("Brindle Loop | AI Engineer")


def test_keyword_filter_needs_remote_and_ai():
    assert looks_relevant("Remote role building LLM agents")
    assert not looks_relevant("Onsite role building LLM agents")
    # "ai" inside "maintaining" must not count
    assert not looks_relevant("Remote role maintaining a billing system")


def test_pick_homepage_skips_job_boards():
    urls = ["https://jobs.lever.co/acme/123", "https://www.acme.example/",
            "https://x.com/acme"]
    assert pick_homepage(urls) == "https://www.acme.example/"
    assert domain_of("https://www.Acme.example/about") == "acme.example"


def test_yc_company_becomes_a_post():
    company = {"id": 7, "name": "Acme", "website": "https://acme.example",
               "batch": "Winter 2026", "team_size": 4, "one_liner": "AI agents for payroll",
               "long_description": "", "tags": ["AI"], "regions": ["Remote", "India"]}
    post = post_from_company(company)
    assert post.source == "yc" and post.urls == ["https://acme.example"]
    assert post_from_company({**company, "regions": ["United States"]}) is None
