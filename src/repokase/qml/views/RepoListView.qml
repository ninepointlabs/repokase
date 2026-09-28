import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Repokase
import "../components"
import "fmt.js" as Fmt

// Toolbar (search, filters, sort) + sortable header + repo list.
// Keys: / or Ctrl+F search, j/k or arrows move, g/G first/last,
// Enter or double-click details, o open on GitHub, c copy URL,
// Ctrl+R refresh, Esc clear search.
FocusScope {
    id: root

    readonly property var list: Repos.list
    property string selectedId: ""
    // Row where a Shift range starts (last plain selection or toggle).
    property int anchorRow: 0
    property string flash: ""
    property var actions
    // Enter / double-click: show the selected repo's details.
    signal openDetail()
    onSelectedIdChanged: Detail.select(selectedId)

    function showFlash(text) { flash = text; copiedTimer.restart() }

    function focusList() { listView.forceActiveFocus(Qt.TabFocusReason) }
    function focusSearch() { search.forceActiveFocus(Qt.ShortcutFocusReason); search.selectAll() }
    function currentRepo() { return listView.currentIndex >= 0 ? list.get(listView.currentIndex) : null }
    function select(i) {
        if (listView.count === 0) return
        listView.currentIndex = Math.max(0, Math.min(listView.count - 1, i))
        const r = currentRepo()
        root.selectedId = r ? r.node_id : ""
    }
    function reselect() {
        const i = root.selectedId ? list.rowOf(root.selectedId) : -1
        listView.currentIndex = i >= 0 ? i : (listView.count > 0 ? 0 : -1)
        const r = currentRepo()
        root.selectedId = r ? r.node_id : ""
    }

    Connections {
        target: Repos.list
        function onChanged() { Qt.callLater(root.reselect) }
    }

    Shortcut { sequences: ["Ctrl+F", "/"]; enabled: !search.activeFocus; onActivated: root.focusSearch() }
    Shortcut { sequences: ["Ctrl+R", "F5"]; onActivated: Repos.refresh() }

    // Column geometry shared by the header and every row. Monospace font, so
    // widths are in character cells.
    QtObject {
        id: geom
        readonly property real cell: Theme.fontSmall * 0.62
        readonly property int padX: Theme.rowPaddingX
        readonly property int gap: Theme.spaceXxl
        readonly property int rowHeight: Theme.fontBody + Theme.fontSmall + Theme.spaceXxs + 2 * Theme.spaceLg + 2
        readonly property int numWidth: Math.ceil(cell * 8)
        readonly property int dateWidth: Math.ceil(cell * 10)
        readonly property int langWidth: Math.ceil(cell * 14)
        readonly property bool showLang: root.width > 820
        readonly property int scrollInset: vbar.visible ? vbar.width : 0
        readonly property bool marking: Repos.markedCount > 0
        readonly property var numeric: [
            { key: "stars", role: "stars", title: "Stars", visible: true },
            { key: "forks", role: "forks", title: "Forks", visible: root.width > 1000 },
            { key: "watchers", role: "watchers", title: "Watch", visible: root.width > 1120 },
            { key: "issues", role: "issues", title: "Issues", visible: root.width > 720 },
            { key: "prs", role: "prs", title: "PRs", visible: root.width > 720 },
        ]
        function showOwner(owner) { return owner !== Auth.login }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ------------------------------------------------------ toolbar
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: toolbar.implicitHeight + 2 * Theme.spaceLg
            color: Theme.bg

            Flow {
                id: toolbar
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: geom.padX
                anchors.rightMargin: geom.padX
                spacing: Theme.spaceLg

                RkTextField {
                    id: search
                    width: Math.min(26 * Theme.fontBody, Math.max(14 * Theme.fontBody, root.width * 0.22))
                    placeholderText: "Search repos, topics, languages"
                    hint: "/"
                    text: Repos.list.search
                    onTextEdited: Repos.list.search = text
                    onTextChanged: if (text === "") Repos.list.search = ""
                    Keys.onEscapePressed: {
                        if (text.length) { clear(); Repos.list.search = "" } else root.focusList()
                    }
                    Keys.onDownPressed: root.focusList()
                    Keys.onReturnPressed: root.focusList()
                    KeyNavigation.tab: visibilityBox
                }

                RkComboBox {
                    id: visibilityBox
                    model: [
                        { text: "All visibility", value: "all" },
                        { text: "Public", value: "public" },
                        { text: "Private", value: "private" },
                        { text: "Internal", value: "internal" },
                    ]
                    current: Repos.list.visibility
                    onPicked: (v) => Repos.list.visibility = v
                }
                RkComboBox {
                    model: [
                        { text: "Hide archived", value: "hide" },
                        { text: "Include archived", value: "include" },
                        { text: "Only archived", value: "only" },
                    ]
                    current: Repos.list.archived
                    onPicked: (v) => Repos.list.archived = v
                }
                RkComboBox {
                    model: [
                        { text: "Include forks", value: "include" },
                        { text: "Hide forks", value: "hide" },
                        { text: "Only forks", value: "only" },
                    ]
                    current: Repos.list.forks
                    onPicked: (v) => Repos.list.forks = v
                }
                RkComboBox {
                    model: [
                        { text: "Any health", value: "any" },
                        { text: "Needs attention", value: "attention" },
                        { text: "Healthy", value: "healthy" },
                    ]
                    current: Repos.list.health
                    onPicked: (v) => Repos.list.health = v
                }
                RkComboBox {
                    visible: Repos.languages.length > 1
                    model: [{ text: "Any language", value: "" }].concat(
                        Repos.languages.map((l) => ({ text: l, value: l })))
                    current: Repos.list.language
                    onPicked: (v) => Repos.list.language = v
                }
                RkComboBox {
                    visible: Repos.owners.length > 1
                    model: [{ text: "Any owner", value: "" }].concat(
                        Repos.owners.map((o) => ({ text: o, value: o })))
                    current: Repos.list.owner
                    onPicked: (v) => Repos.list.owner = v
                }
                RkComboBox {
                    label: "Sort"
                    model: [
                        { text: "Last push", value: "pushed" },
                        { text: "Health", value: "health" },
                        { text: "Name", value: "name" },
                        { text: "Stars", value: "stars" },
                        { text: "Forks", value: "forks" },
                        { text: "Watchers", value: "watchers" },
                        { text: "Open issues", value: "issues" },
                        { text: "Open PRs", value: "prs" },
                        { text: "Language", value: "language" },
                        { text: "Visibility", value: "visibility" },
                        { text: "Archived", value: "archived" },
                        { text: "Description", value: "description" },
                        { text: "Updated", value: "updated" },
                        { text: "Created", value: "created" },
                    ]
                    current: Repos.list.sortKey
                    accentNonDefault: false
                    onPicked: (v) => Repos.list.sortKey = v
                }
                RkButton {
                    text: Repos.list.descending ? "↓" : "↑"
                    implicitWidth: Theme.controlHeight
                    onClicked: Repos.list.descending = !Repos.list.descending
                    Accessible.name: Repos.list.descending ? "Sort descending" : "Sort ascending"
                }
                RkButton {
                    visible: Repos.list.filtered
                    variant: "ghost"
                    text: "Clear"
                    onClicked: { Repos.list.resetFilters(); search.clear() }
                }
            }
        }

        RkBusyBar { Layout.fillWidth: true; running: Repos.refreshing }

        // ------------------------------------------------------ bulk bar
        Rectangle {
            Layout.fillWidth: true
            visible: Repos.markedCount > 0
            implicitHeight: bulkRow.implicitHeight + 2 * Theme.spaceMd
            color: Theme.tint(Theme.accent, 0.10)
            Rectangle { anchors { left: parent.left; top: parent.top; bottom: parent.bottom } width: 3; color: Theme.accent }

            Flow {
                id: bulkRow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: geom.padX
                anchors.rightMargin: geom.padX
                spacing: Theme.spaceMd

                RkText {
                    height: Theme.controlHeight
                    verticalAlignment: Text.AlignVCenter
                    text: Repos.markedCount + " marked" + (Repos.hiddenMarked > 0 ? " (" + Repos.hiddenMarked + " hidden by filters)" : "")
                    font.weight: Font.DemiBold
                }
                RkButton { text: "Archive"; enabled: !Actions.busy; onClicked: root.actions.bulkArchive(true) }
                RkButton { text: "Unarchive"; enabled: !Actions.busy; onClicked: root.actions.bulkArchive(false) }
                RkComboBox {
                    visible: Repos.categories.length > 0
                    accentNonDefault: false
                    model: [{ text: "Category…", value: "" }]
                        .concat(Repos.categories.map((c) => ({ text: "Add to " + c.name, value: "add:" + c.id })))
                        .concat(Repos.categories.map((c) => ({ text: "Remove from " + c.name, value: "rm:" + c.id })))
                    current: ""
                    onPicked: (v) => {
                        if (!v) return
                        const [op, id] = v.split(":")
                        Repos.setCategoryForMarked(parseInt(id), op === "add")
                        root.showFlash((op === "add" ? "Added " : "Removed ") + Repos.markedCount + " repos")
                        currentIndex = 0
                    }
                }
                RkButton { text: "Mark all"; variant: "ghost"; hint: "Ctrl+A"; onClicked: Repos.markAllVisible() }
                RkButton { text: "Clear"; variant: "ghost"; hint: "Esc"; onClicked: Repos.clearMarks() }
            }
        }
        Rectangle { Layout.fillWidth: true; height: Theme.borderWidth; color: Theme.border; visible: !Repos.refreshing }

        RkNotice {
            Layout.fillWidth: true
            Layout.margins: Theme.spaceLg
            kind: "danger"
            text: Repos.error
        }
        // Action failures, with a one-click SSO authorization when GitHub offers it.
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.spaceLg
            visible: Actions.error.length > 0
            spacing: Theme.spaceMd
            RkNotice { Layout.fillWidth: true; kind: "danger"; text: Actions.error }
            RkButton { visible: Actions.errorUrl.length > 0; text: "Authorize SSO"; variant: "primary"; onClicked: Repos.openUrl(Actions.errorUrl) }
            RkButton { text: "Dismiss"; variant: "ghost"; onClicked: Actions.clearError() }
        }
        Repeater {
            model: Repos.warnings
            RkNotice {
                required property string modelData
                Layout.fillWidth: true
                Layout.leftMargin: Theme.spaceLg
                Layout.rightMargin: Theme.spaceLg
                Layout.topMargin: Theme.spaceSm
                kind: "warning"
                text: modelData
            }
        }

        // ------------------------------------------------------- header
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Theme.controlHeight
            color: Theme.bgSunken

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: geom.padX
                anchors.rightMargin: geom.padX + geom.scrollInset
                spacing: geom.gap

                RkHeaderCell {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 0
                    text: "Repository"
                    key: "name"; align: Text.AlignLeft
                    activeKey: Repos.list.sortKey; descending: Repos.list.descending
                    onClicked: Repos.list.sortBy(key)
                }
                RkHeaderCell {
                    Layout.preferredWidth: geom.langWidth
                    Layout.minimumWidth: geom.langWidth
                    visible: geom.showLang
                    text: "Language"
                    key: "language"; align: Text.AlignLeft
                    activeKey: Repos.list.sortKey; descending: Repos.list.descending
                    onClicked: Repos.list.sortBy(key)
                }
                Repeater {
                    model: geom.numeric
                    RkHeaderCell {
                        required property var modelData
                        Layout.preferredWidth: geom.numWidth
                        Layout.minimumWidth: geom.numWidth
                        visible: modelData.visible
                        text: modelData.title
                        key: modelData.key
                        activeKey: Repos.list.sortKey; descending: Repos.list.descending
                        onClicked: Repos.list.sortBy(key)
                    }
                }
                RkHeaderCell {
                    Layout.preferredWidth: geom.dateWidth
                    Layout.minimumWidth: geom.dateWidth
                    text: "Pushed"
                    key: "pushed"
                    activeKey: Repos.list.sortKey; descending: Repos.list.descending
                    onClicked: Repos.list.sortBy(key)
                }
            }
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: Theme.borderWidth
                color: Theme.border
            }
        }

        // --------------------------------------------------------- list
        ListView {
            id: listView
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            focus: true
            activeFocusOnTab: true
            model: Repos.list
            currentIndex: -1
            boundsBehavior: Flickable.StopAtBounds
            keyNavigationEnabled: true
            highlightMoveDuration: 0
            reuseItems: true
            T.ScrollBar.vertical: RkScrollBar { id: vbar }

            readonly property int pageRows: Math.max(1, Math.floor(height / geom.rowHeight) - 1)

            delegate: RepoRow {
                cols: geom
                selected: ListView.isCurrentItem
                keyboardFocus: listView.activeFocus
                onPicked: (mods) => {
                    if (mods & Qt.ShiftModifier) {
                        Repos.markRange(root.anchorRow, index)
                    } else if (mods & Qt.ControlModifier) {
                        Repos.toggleMark(nodeId)
                        root.anchorRow = index
                    } else {
                        root.anchorRow = index
                    }
                    root.select(index)
                    listView.forceActiveFocus(Qt.MouseFocusReason)
                }
                onActivated: { root.select(index); root.openDetail() }
            }

            onCurrentIndexChanged: {
                const r = root.currentRepo()
                if (r) root.selectedId = r.node_id
            }

            Keys.onPressed: (event) => {
                const r = root.currentRepo()
                // Bulk marking.
                if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_A) {
                    Repos.markAllVisible(); event.accepted = true; return
                }
                if ((event.modifiers & Qt.ShiftModifier) && [Qt.Key_Down, Qt.Key_Up, Qt.Key_J, Qt.Key_K].indexOf(event.key) >= 0) {
                    if (r) Repos.setMarked(r.node_id, true)
                    root.select(currentIndex + ((event.key === Qt.Key_Down || event.key === Qt.Key_J) ? 1 : -1))
                    const n = root.currentRepo()
                    if (n) Repos.setMarked(n.node_id, true)
                    event.accepted = true; return
                }
                if (event.key === Qt.Key_Escape && Repos.markedCount > 0) {
                    Repos.clearMarks(); event.accepted = true; return
                }
                if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier)) return
                switch (event.key) {
                case Qt.Key_X:
                case Qt.Key_Space:
                    if (r) { Repos.toggleMark(r.node_id); root.anchorRow = currentIndex } break
                case Qt.Key_J: root.select(currentIndex + 1); break
                case Qt.Key_K: root.select(currentIndex - 1); break
                case Qt.Key_G:
                    root.select(event.modifiers & Qt.ShiftModifier ? count - 1 : 0); break
                case Qt.Key_Home: root.select(0); break
                case Qt.Key_End: root.select(count - 1); break
                case Qt.Key_PageDown: root.select(currentIndex + pageRows); break
                case Qt.Key_PageUp: root.select(currentIndex - pageRows); break
                case Qt.Key_Return:
                case Qt.Key_Enter:
                case Qt.Key_L:
                case Qt.Key_Right:
                    if (r) root.openDetail(); break
                case Qt.Key_O:
                    if (r) Repos.openUrl(r.url); break
                case Qt.Key_E:
                    if (r) root.actions.editDescription(r.node_id); break
                case Qt.Key_A:
                    if (!(event.modifiers & Qt.ShiftModifier)) return
                    if (r) root.actions.toggleArchive(r.node_id); break
                case Qt.Key_V:
                    if (!(event.modifiers & Qt.ShiftModifier)) return
                    if (r) root.actions.changeVisibility(r.node_id); break
                case Qt.Key_Delete:
                    if (r) root.actions.remove(r.node_id); break
                case Qt.Key_C:
                    if (r) { Repos.copy(r.url); root.showFlash("Copied URL") } break
                case Qt.Key_1: case Qt.Key_2: case Qt.Key_3:
                case Qt.Key_4: case Qt.Key_5: case Qt.Key_6:
                case Qt.Key_7: case Qt.Key_8: case Qt.Key_9: {
                    const cid = Repos.categoryIdAt(event.key - Qt.Key_0)
                    if (r && cid >= 0) {
                        const had = (r.category_ids || []).indexOf(cid) >= 0
                        Repos.toggleCategory(r.node_id, cid)
                        const cat = Repos.categories.find((c) => c.id === cid)
                        root.showFlash((had ? "Removed from " : "Added to ") + (cat ? cat.name : "category"))
                    }
                    break
                }
                case Qt.Key_Escape:
                    if (Repos.list.search.length) { search.clear(); Repos.list.search = "" } break
                default: return
                }
                event.accepted = true
            }

            // ---------------------------------------------- empty states
            ColumnLayout {
                anchors.centerIn: parent
                visible: listView.count === 0
                spacing: Theme.spaceLg
                RkText {
                    Layout.alignment: Qt.AlignHCenter
                    role: "title"
                    text: Repos.total === 0
                        ? (Repos.refreshing ? "Fetching your repositories…" : "No repositories yet")
                        : "No repositories match"
                }
                RkText {
                    Layout.alignment: Qt.AlignHCenter
                    muted: true
                    visible: Repos.total > 0
                    text: Repos.total + " hidden by the current search and filters"
                }
                RkButton {
                    Layout.alignment: Qt.AlignHCenter
                    visible: Repos.total > 0
                    text: "Clear filters"
                    onClicked: { Repos.list.resetFilters(); search.clear() }
                }
            }
        }

        // --------------------------------------------------- status bar
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: status.implicitHeight + 2 * Theme.spaceSm
            color: Theme.bgSunken
            Rectangle {
                anchors { left: parent.left; right: parent.right; top: parent.top }
                height: Theme.borderWidth
                color: Theme.border
            }

            RowLayout {
                id: status
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: geom.padX
                anchors.rightMargin: geom.padX
                spacing: Theme.spaceXxl

                RkText {
                    role: "caption"
                    text: Actions.busy ? Actions.busyLabel
                        : Workflows.busy ? Workflows.busyLabel
                        : Traffic.running ? Traffic.progress
                        : copiedTimer.running ? root.flash
                        : Repos.list.count === Repos.total ? Repos.total + " repos"
                        : Repos.list.count + " of " + Repos.total + " repos"
                    color: Actions.busy || Workflows.busy || Traffic.running ? Theme.warning : copiedTimer.running ? Theme.success : Theme.fgSecondary
                }
                RkText {
                    role: "caption"
                    muted: true
                    text: Repos.refreshing ? Repos.progress
                        : "Synced " + Fmt.agoMs(Repos.lastSynced, Repos.now)
                }
                Item { Layout.fillWidth: true }
                RkText {
                    role: "caption"
                    muted: true
                    text: "Enter details · o GitHub · c copy · 1–9 category · / search"
                    visible: root.width > 900
                }
                RkText {
                    role: "caption"
                    visible: Auth.rateRemaining >= 0
                    color: Auth.rateRemaining < Auth.rateLimit * 0.1 ? Theme.warning : Theme.fgMuted
                    text: "API " + Auth.rateRemaining + "/" + Auth.rateLimit
                        + (Auth.rateResetAt > 0 ? " · resets " + Fmt.clock(Auth.rateResetAt) : "")
                }
                RkText {
                    role: "caption"
                    muted: true
                    text: Theme.name + (Theme.source === "fallback" ? " (fallback)" : "")
                }
            }
        }
    }

    Timer { id: copiedTimer; interval: 1800 }

    Component.onCompleted: { root.reselect(); root.focusList() }
}
