"""Qt models over cached repositories: the list and its sort/filter proxy."""

from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
    Slot,
)

# QML role name -> repo dict key.
ROLES: dict[str, str] = {
    "nodeId": "node_id",
    "owner": "owner",
    "name": "name",
    "fullName": "full_name",
    "description": "description",
    "url": "url",
    "visibility": "visibility",
    "isArchived": "is_archived",
    "isFork": "is_fork",
    "isTemplate": "is_template",
    "isMirror": "is_mirror",
    "language": "primary_language",
    "stars": "stargazers",
    "forks": "forks",
    "watchers": "watchers",
    "issues": "open_issues",
    "prs": "open_prs",
    "defaultBranch": "default_branch",
    "license": "license_spdx",
    "permission": "viewer_permission",
    "pushedAt": "pushed_at",
    "createdAt": "created_at",
    "updatedAt": "updated_at",
    "topics": "topics",
    "categoryIds": "category_ids",
    "health": "health",
    "marked": "marked",
}
ROLE_IDS = {name: Qt.UserRole + 1 + i for i, name in enumerate(ROLES)}
KEY_FOR_ROLE = {ROLE_IDS[name]: key for name, key in ROLES.items()}

# Sort keys the UI offers -> repo dict key. Text sorts ascending by default,
# counts and dates descending (biggest / newest first).
SORT_KEYS: dict[str, str] = {
    "name": "full_name",
    "description": "description",
    "visibility": "visibility",
    "language": "primary_language",
    "stars": "stargazers",
    "forks": "forks",
    "watchers": "watchers",
    "issues": "open_issues",
    "prs": "open_prs",
    "pushed": "pushed_at",
    "updated": "updated_at",
    "created": "created_at",
    "archived": "is_archived",
    "health": "health",
}
DESC_BY_DEFAULT = {"health", "stars", "forks", "watchers", "issues", "prs", "pushed", "updated", "created", "archived"}


class RepoListModel(QAbstractListModel):
    countChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._repos: list[dict] = []
        self._row_of: dict[str, int] = {}

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._repos)

    def roleNames(self):
        return {rid: QByteArray(name.encode()) for name, rid in ROLE_IDS.items()}

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._repos):
            return None
        repo = self._repos[index.row()]
        if role == Qt.DisplayRole:
            return repo["full_name"]
        key = KEY_FOR_ROLE.get(role)
        if key is None:
            return None
        value = repo.get(key)
        if value is None and key in ("description", "primary_language", "license_spdx", "pushed_at"):
            return ""
        if value is None and key == "marked":
            return False
        return value

    def repo_at(self, row: int) -> dict | None:
        return self._repos[row] if 0 <= row < len(self._repos) else None

    def row_of(self, node_id: str) -> int:
        return self._row_of.get(node_id, -1)

    def repos(self) -> list[dict]:
        return self._repos

    def get_repo(self, node_id: str) -> dict | None:
        return self.repo_at(self.row_of(node_id))

    def update_repo(self, node_id: str, **changes) -> dict | None:
        """Patch one repo in place; proxies re-sort/re-filter just that row."""
        row = self.row_of(node_id)
        if row < 0:
            return None
        repo = dict(self._repos[row], **changes)
        self._repos[row] = repo
        idx = self.index(row)
        self.dataChanged.emit(idx, idx)
        return repo

    def remove_repo(self, node_id: str) -> bool:
        row = self.row_of(node_id)
        if row < 0:
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._repos[row]
        self._row_of = {r["node_id"]: i for i, r in enumerate(self._repos)}
        self.endRemoveRows()
        self.countChanged.emit()
        return True

    def set_repos(self, repos: list[dict]) -> None:
        """Replace contents, emitting fine-grained changes when the set is unchanged."""
        new_ids = [r["node_id"] for r in repos]
        if new_ids == [r["node_id"] for r in self._repos]:
            self._repos = list(repos)
            if self._repos:
                self.dataChanged.emit(self.index(0), self.index(len(self._repos) - 1))
            return
        self.beginResetModel()
        self._repos = list(repos)
        self._row_of = {nid: i for i, nid in enumerate(new_ids)}
        self.endResetModel()
        self.countChanged.emit()

    count = Property(int, lambda self: len(self._repos), notify=countChanged)


HEALTH_RANK = {"unknown": -1, "ok": 0, "info": 1, "warning": 2, "serious": 3, "critical": 4}
ATTENTION = {"warning", "serious", "critical"}


def _health_rank(h) -> int:
    return HEALTH_RANK.get((h or {}).get("level", "unknown"), -1)


def _matches(repo: dict, terms: list[str]) -> bool:
    haystack = " ".join(
        filter(
            None,
            (
                repo.get("full_name"),
                repo.get("description"),
                repo.get("primary_language"),
                " ".join(repo.get("topics") or []),
            ),
        )
    ).lower()
    return all(t in haystack for t in terms)


class RepoFilterModel(QSortFilterProxyModel):
    """Sorting, filters and text search. All state is QML-bindable."""

    changed = Signal()

    def __init__(self, source: RepoListModel, parent=None):
        super().__init__(parent)
        self.setSourceModel(source)
        self._source = source
        self._search = ""
        self._terms: list[str] = []
        self._sort_key = "pushed"
        self._descending = True
        self._visibility = "all"  # all | public | private | internal
        self._archived = "hide"  # hide | include | only
        self._forks = "include"  # include | hide | only
        self._language = ""  # "" = any
        self._owner = ""  # "" = any owner login
        self._category = -1  # -1 = any, 0 = uncategorized, >0 = category id
        self._health = "any"  # any | attention | healthy
        self.setDynamicSortFilter(True)
        self.sort(0, Qt.DescendingOrder)
        source.countChanged.connect(self.changed)
        self.rowsInserted.connect(self.changed)
        self.rowsRemoved.connect(self.changed)
        self.modelReset.connect(self.changed)
        self.layoutChanged.connect(self.changed)

    # ---------------------------------------------------------------- core
    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        repo = self._source.repo_at(row)
        if repo is None:
            return False
        if self._visibility != "all" and repo["visibility"].lower() != self._visibility:
            return False
        archived = bool(repo.get("is_archived"))
        if (self._archived == "hide" and archived) or (self._archived == "only" and not archived):
            return False
        fork = bool(repo.get("is_fork"))
        if (self._forks == "hide" and fork) or (self._forks == "only" and not fork):
            return False
        if self._language and (repo.get("primary_language") or "") != self._language:
            return False
        if self._owner and repo.get("owner") != self._owner:
            return False
        level = (repo.get("health") or {}).get("level", "unknown")
        if self._health == "attention" and level not in ATTENTION:
            return False
        if self._health == "healthy" and level not in ("ok", "info"):
            return False
        if self._category == 0 and repo.get("category_ids"):
            return False
        if self._category > 0 and self._category not in (repo.get("category_ids") or []):
            return False
        return not self._terms or _matches(repo, self._terms)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        a = self._source.repo_at(left.row())
        b = self._source.repo_at(right.row())
        key = SORT_KEYS[self._sort_key]
        va, vb = a.get(key), b.get(key)
        a_missing, b_missing = va is None or va == "", vb is None or vb == ""
        if key == "health":
            va, vb = _health_rank(va), _health_rank(vb)
            a_missing = b_missing = False
        if a_missing != b_missing:
            # Missing values (no language, never pushed) sort last in either
            # direction. Qt reverses lessThan for descending order, so a
            # missing value is "greater" ascending and "smaller" descending.
            return a_missing if self._descending else b_missing
        if isinstance(va, str) and isinstance(vb, str):
            va, vb = va.lower(), vb.lower()
        if a_missing or va == vb:
            # Stable tiebreak on name, always ascending regardless of direction.
            na, nb = a["full_name"].lower(), b["full_name"].lower()
            return (na > nb) if self._descending else (na < nb)
        return va < vb

    @contextmanager
    def _filter_change(self):
        """Wrap every filter-parameter change (Qt 6.10+ begin/endFilterChange)."""
        self.beginFilterChange()
        try:
            yield
        finally:
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        self.changed.emit()

    # ------------------------------------------------------------ bindings
    def _setter(attr: str):
        def setter(self, value):
            if getattr(self, attr) == value:
                return
            with self._filter_change():
                setattr(self, attr, value)

        return setter

    def _set_search(self, text: str) -> None:
        if text == self._search:
            return
        with self._filter_change():
            self._search = text
            self._terms = [t for t in text.lower().split() if t]

    def _set_sort_key(self, key: str) -> None:
        if key not in SORT_KEYS or key == self._sort_key:
            return
        self._sort_key = key
        self._descending = key in DESC_BY_DEFAULT
        self._resort()

    def _set_descending(self, value: bool) -> None:
        if value == self._descending:
            return
        self._descending = value
        self._resort()

    def _resort(self) -> None:
        self.invalidate()
        self.sort(0, Qt.DescendingOrder if self._descending else Qt.AscendingOrder)
        self.changed.emit()

    @Slot(str)
    def sortBy(self, key: str) -> None:
        """Header click: new key picks its natural direction; same key flips."""
        if key == self._sort_key:
            self._set_descending(not self._descending)
        else:
            self._set_sort_key(key)

    @Slot(int, result="QVariant")
    def get(self, row: int):
        idx = self.index(row, 0)
        if not idx.isValid():
            return None
        return self._source.repo_at(self.mapToSource(idx).row())

    @Slot(str, result=int)
    def rowOf(self, node_id: str) -> int:
        src = self._source.row_of(node_id)
        if src < 0:
            return -1
        return self.mapFromSource(self._source.index(src)).row()

    @Slot()
    def resetFilters(self) -> None:
        with self._filter_change():
            self._search, self._terms = "", []
            self._visibility, self._archived, self._forks = "all", "hide", "include"
            self._language, self._owner, self._category = "", "", -1
            self._health = "any"

    def state(self) -> dict:
        return {
            "sortKey": self._sort_key,
            "descending": self._descending,
            "visibility": self._visibility,
            "archived": self._archived,
            "forks": self._forks,
            "language": self._language,
            "owner": self._owner,
            "health": self._health,
        }

    def restore(self, state: dict) -> None:
        if not isinstance(state, dict):
            return
        if state.get("sortKey") in SORT_KEYS:
            self._sort_key = state["sortKey"]
            self._descending = bool(state.get("descending", self._sort_key in DESC_BY_DEFAULT))
        with self._filter_change():
            for key, attr, allowed in (
                ("visibility", "_visibility", {"all", "public", "private", "internal"}),
                ("archived", "_archived", {"hide", "include", "only"}),
                ("forks", "_forks", {"include", "hide", "only"}),
                ("health", "_health", {"any", "attention", "healthy"}),
            ):
                if state.get(key) in allowed:
                    setattr(self, attr, state[key])
            for key, attr in (("language", "_language"), ("owner", "_owner")):
                if isinstance(state.get(key), str):
                    setattr(self, attr, state[key])
        self._resort()

    search = Property(str, lambda self: self._search, _set_search, notify=changed)
    sortKey = Property(str, lambda self: self._sort_key, _set_sort_key, notify=changed)
    descending = Property(bool, lambda self: self._descending, _set_descending, notify=changed)
    visibility = Property(str, lambda self: self._visibility, _setter("_visibility"), notify=changed)
    archived = Property(str, lambda self: self._archived, _setter("_archived"), notify=changed)
    forks = Property(str, lambda self: self._forks, _setter("_forks"), notify=changed)
    language = Property(str, lambda self: self._language, _setter("_language"), notify=changed)
    owner = Property(str, lambda self: self._owner, _setter("_owner"), notify=changed)
    category = Property(int, lambda self: self._category, _setter("_category"), notify=changed)
    health = Property(str, lambda self: self._health, _setter("_health"), notify=changed)
    count = Property(int, lambda self: self.rowCount(), notify=changed)
    filtered = Property(
        bool,
        lambda self: bool(
            self._terms
            or self._visibility != "all"
            or self._archived != "hide"
            or self._forks != "include"
            or self._language
            or self._owner
            or self._category != -1
            or self._health != "any"
        ),
        notify=changed,
    )

    del _setter
