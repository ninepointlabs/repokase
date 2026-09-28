import pytest
from PySide6.QtCore import QCoreApplication

from repokase.models.repo_model import ROLE_IDS, RepoFilterModel, RepoListModel


@pytest.fixture(scope="module")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def r(node_id, full_name, **kw):
    base = {
        "node_id": node_id,
        "owner": full_name.split("/")[0],
        "name": full_name.split("/")[1],
        "full_name": full_name,
        "description": None,
        "url": "https://github.com/" + full_name,
        "visibility": "PUBLIC",
        "is_archived": False,
        "is_fork": False,
        "primary_language": None,
        "stargazers": 0,
        "forks": 0,
        "watchers": 0,
        "open_issues": 0,
        "open_prs": 0,
        "pushed_at": None,
        "topics": [],
        "category_ids": [],
    }
    base.update(kw)
    return base


REPOS = [
    r("1", "me/alpha", stargazers=10, primary_language="Python", pushed_at="2026-09-01T00:00:00Z",
      description="Terminal email client", topics=["cli"]),
    r("2", "me/beta", stargazers=3, primary_language="Go", pushed_at="2026-09-20T00:00:00Z", visibility="PRIVATE"),
    r("3", "org/gamma", stargazers=3, primary_language=None, pushed_at=None, is_fork=True),
    r("4", "me/delta", stargazers=50, primary_language="Python", pushed_at="2025-01-01T00:00:00Z",
      is_archived=True, category_ids=[7]),
]


@pytest.fixture
def models(qapp):
    src = RepoListModel()
    src.set_repos(REPOS)
    proxy = RepoFilterModel(src)
    return src, proxy


def names(proxy):
    return [proxy.get(i)["full_name"] for i in range(proxy.rowCount())]


def test_default_hides_archived_and_sorts_by_push_newest_first(models):
    _, proxy = models
    # Never-pushed repos sort last even in descending order.
    assert names(proxy) == ["me/beta", "me/alpha", "org/gamma"]


def test_sort_by_stars_desc_with_name_tiebreak(models):
    _, proxy = models
    proxy.archived = "include"
    proxy.sortKey = "stars"
    assert proxy.descending is True
    assert names(proxy) == ["me/delta", "me/alpha", "me/beta", "org/gamma"]


def test_sort_by_name_and_flip(models):
    _, proxy = models
    proxy.sortBy("name")
    assert proxy.descending is False
    assert names(proxy) == ["me/alpha", "me/beta", "org/gamma"]
    proxy.sortBy("name")
    assert names(proxy) == ["org/gamma", "me/beta", "me/alpha"]


def test_missing_language_sorts_last_both_directions(models):
    _, proxy = models
    proxy.sortKey = "language"
    assert names(proxy)[-1] == "org/gamma"
    proxy.descending = True
    assert names(proxy)[-1] == "org/gamma"


def test_filters(models):
    _, proxy = models
    proxy.visibility = "private"
    assert names(proxy) == ["me/beta"]
    proxy.visibility = "all"
    proxy.forks = "only"
    assert names(proxy) == ["org/gamma"]
    proxy.forks = "hide"
    proxy.archived = "only"
    assert names(proxy) == ["me/delta"]
    proxy.archived = "include"
    proxy.forks = "include"
    proxy.language = "Python"
    assert set(names(proxy)) == {"me/alpha", "me/delta"}
    proxy.language = ""
    proxy.owner = "org"
    assert names(proxy) == ["org/gamma"]
    proxy.owner = ""
    proxy.category = 7
    assert names(proxy) == ["me/delta"]
    proxy.category = 0
    assert "me/delta" not in names(proxy)
    assert proxy.filtered
    proxy.resetFilters()
    assert not proxy.filtered and proxy.rowCount() == 3


def test_search_matches_all_terms_across_fields(models):
    _, proxy = models
    proxy.search = "email"
    assert names(proxy) == ["me/alpha"]
    proxy.search = "CLI python"  # topic + language, case-insensitive
    assert names(proxy) == ["me/alpha"]
    proxy.search = "cli go"
    assert names(proxy) == []
    proxy.search = "gamma"
    assert names(proxy) == ["org/gamma"]


def test_state_roundtrip_and_bad_state_ignored(models):
    src, proxy = models
    proxy.sortKey = "prs"
    proxy.visibility = "private"
    state = proxy.state()
    other = RepoFilterModel(src)
    other.restore(state)
    assert other.sortKey == "prs" and other.visibility == "private"
    other.restore({"sortKey": "bogus", "visibility": "secret", "archived": 3})
    assert other.sortKey == "prs" and other.visibility == "private"


def test_row_lookup_and_roles(models):
    src, proxy = models
    assert proxy.rowOf("2") == 0
    assert proxy.rowOf("4") == -1  # filtered out
    idx = src.index(src.row_of("1"))
    assert src.data(idx, ROLE_IDS["stars"]) == 10
    assert src.data(idx, ROLE_IDS["language"]) == "Python"
    assert src.data(src.index(src.row_of("3")), ROLE_IDS["language"]) == ""


def test_set_repos_same_ids_is_not_a_reset(models):
    src, proxy = models
    resets = []
    src.modelReset.connect(lambda: resets.append(1))
    src.set_repos([dict(x, stargazers=x["stargazers"] + 1) for x in REPOS])
    assert resets == []
    assert proxy.get(0)["stargazers"] == 4  # me/beta, updated in place
    src.set_repos(REPOS[:2])
    assert resets == [1]
