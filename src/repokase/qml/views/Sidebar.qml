import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Repokase
import "../components"

// Category filter list. Keys: arrows/j/k move, Enter select, n new,
// F2 rename, Delete remove, Alt+Up/Down reorder.
// Below it, organizations that own repos in the list. Keys: arrows/j/k move,
// Enter filter (again to clear), o open on GitHub.
Rectangle {
    id: root
    property var dialogs

    color: Theme.bgSunken
    // About 22 characters, but never narrower than the widest fixed control,
    // or the column overflows and clips the counts.
    implicitWidth: Math.ceil(Math.max(22 * Theme.fontBody * 0.62 + 2 * Theme.rowPaddingX,
                            missingOrg.implicitWidth + missingOrg.Layout.leftMargin + Theme.rowPaddingX + Theme.borderWidth))

    readonly property var entries: [
        { id: -1, name: "All repositories", count: Repos.total, fixed: true },
        { id: 0, name: "Uncategorized", count: Repos.uncategorized, fixed: true },
    ].concat(Repos.categories.map((c) => ({ id: c.id, name: c.name, count: c.count, position: c.position, fixed: false })))

    function focusList() { list.forceActiveFocus(Qt.TabFocusReason) }
    function orgUrl(login, page) {
        return page === "people" ? "https://github.com/orgs/" + login + "/people"
            : page === "settings" ? "https://github.com/organizations/" + login + "/settings/profile"
            : "https://github.com/" + login
    }
    function toggleOrg(login) { Repos.list.owner = Repos.list.owner === login ? "" : login }
    function syncIndex() {
        for (let i = 0; i < entries.length; i++) if (entries[i].id === Repos.list.category) { list.currentIndex = i; return }
        list.currentIndex = 0
    }
    onEntriesChanged: Qt.callLater(syncIndex)
    Connections { target: Repos.list; function onChanged() { root.syncIndex() } }

    Rectangle {
        anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
        width: Theme.borderWidth
        color: Theme.border
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.rightMargin: Theme.borderWidth
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.rowPaddingX
            Layout.rightMargin: Theme.spaceSm
            Layout.topMargin: Theme.spaceLg
            Layout.bottomMargin: Theme.spaceSm
            RkText { Layout.fillWidth: true; text: "CATEGORIES"; role: "caption"; muted: true; font.letterSpacing: 1 }
            RkButton {
                variant: "ghost"
                text: "+"
                implicitWidth: Theme.controlHeight
                focusPolicy: Qt.TabFocus
                onClicked: root.dialogs.create(root.focusList)
                Accessible.name: "New category"
            }
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            activeFocusOnTab: true
            model: root.entries
            keyNavigationEnabled: true
            boundsBehavior: Flickable.StopAtBounds
            highlightMoveDuration: 0
            T.ScrollBar.vertical: RkScrollBar {}

            function current() { return currentIndex >= 0 ? root.entries[currentIndex] : null }

            Keys.onPressed: (e) => {
                const c = current()
                if ((e.key === Qt.Key_Up || e.key === Qt.Key_Down) && (e.modifiers & Qt.AltModifier)) {
                    if (c && !c.fixed) Repos.moveCategory(c.id, e.key === Qt.Key_Up ? -1 : 1)
                } else if (e.key === Qt.Key_J) {
                    incrementCurrentIndex()
                } else if (e.key === Qt.Key_K) {
                    decrementCurrentIndex()
                } else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) {
                    if (c) Repos.list.category = c.id
                } else if (e.key === Qt.Key_N) {
                    root.dialogs.create(root.focusList)
                } else if (e.key === Qt.Key_F2) {
                    if (c && !c.fixed) root.dialogs.rename(c.id, c.name, root.focusList)
                } else if (e.key === Qt.Key_Delete) {
                    if (c && !c.fixed) root.dialogs.remove(c.id, c.name, c.count, root.focusList)
                } else return
                e.accepted = true
            }

            delegate: Item {
                id: entry
                required property var modelData
                required property int index
                readonly property bool active: Repos.list.category === modelData.id
                width: ListView.view.width
                height: Theme.controlHeight

                Rectangle {
                    anchors.fill: parent
                    color: entry.active ? Theme.selectedFill : mouse.containsMouse ? Theme.hoverFill : "transparent"
                }
                Rectangle {
                    visible: entry.active
                    width: 2
                    anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                    color: Theme.accent
                }
                RkFocusFrame { shown: list.activeFocus && entry.ListView.isCurrentItem; anchors.margins: 0 }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.rowPaddingX
                    anchors.rightMargin: Theme.rowPaddingX
                    spacing: Theme.spaceMd
                    RkText {
                        visible: !entry.modelData.fixed
                        Layout.preferredWidth: Theme.fontCaption
                        text: entry.modelData.position < 9 ? String(entry.modelData.position + 1) : ""
                        role: "caption"
                        muted: true
                    }
                    Rectangle {
                        visible: !entry.modelData.fixed
                        width: Theme.spaceMd; height: width
                        radius: Theme.radius > 0 ? width / 2 : 0
                        color: Theme.seriesAt(entry.modelData.position || 0)
                    }
                    RkText {
                        Layout.fillWidth: true
                        text: entry.modelData.name
                        color: entry.active ? Theme.accent : Theme.fg
                        font.italic: entry.modelData.id === 0
                    }
                    RkText {
                        text: entry.modelData.count
                        role: "small"
                        muted: true
                    }
                }

                MouseArea {
                    id: mouse
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onClicked: (m) => {
                        list.currentIndex = entry.index
                        Repos.list.category = entry.modelData.id
                    }
                    onDoubleClicked: if (!entry.modelData.fixed) root.dialogs.rename(entry.modelData.id, entry.modelData.name, root.focusList)
                }
            }
        }

        RkText {
            Layout.fillWidth: true
            Layout.margins: Theme.rowPaddingX
            visible: Repos.categories.length === 0
            text: "Press n to create a category, then 1–9 in the list to assign."
            role: "caption"
            muted: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }
        RkText {
            Layout.fillWidth: true
            Layout.margins: Theme.rowPaddingX
            visible: Repos.categories.length > 0
            text: "n new · F2 rename · Del remove · Alt+↑↓ move"
            role: "caption"
            muted: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }

        // ------------------------------------------------------ organizations
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Theme.borderWidth
            color: Theme.border
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.rowPaddingX
            Layout.rightMargin: Theme.spaceSm
            Layout.topMargin: Theme.spaceLg
            Layout.bottomMargin: Theme.spaceSm
            RkText { Layout.fillWidth: true; text: "ORGANIZATIONS"; role: "caption"; muted: true; font.letterSpacing: 1 }
            RkButton {
                variant: "ghost"
                text: "+"
                implicitWidth: Theme.controlHeight
                focusPolicy: Qt.TabFocus
                // GitHub's API cannot create organizations; this is the web form.
                onClicked: Repos.openUrl("https://github.com/account/organizations/new")
                Accessible.name: "New organization on GitHub"
            }
        }

        ListView {
            id: orgList
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(count, 6) * Theme.controlHeight
            visible: count > 0
            clip: true
            activeFocusOnTab: true
            model: Repos.organizations
            keyNavigationEnabled: true
            boundsBehavior: Flickable.StopAtBounds
            highlightMoveDuration: 0
            T.ScrollBar.vertical: RkScrollBar {}

            function current() { return currentIndex >= 0 ? Repos.organizations[currentIndex] : null }

            Keys.onPressed: (e) => {
                const c = current()
                if (e.key === Qt.Key_J) incrementCurrentIndex()
                else if (e.key === Qt.Key_K) decrementCurrentIndex()
                else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { if (c) root.toggleOrg(c.login) }
                else if (e.key === Qt.Key_O) { if (c) Repos.openUrl(root.orgUrl(c.login)) }
                else return
                e.accepted = true
            }

            delegate: Item {
                id: org
                required property var modelData
                required property int index
                readonly property bool active: Repos.list.owner === modelData.login
                width: ListView.view.width
                height: Theme.controlHeight

                Rectangle {
                    anchors.fill: parent
                    color: org.active ? Theme.selectedFill : orgMouse.containsMouse ? Theme.hoverFill : "transparent"
                }
                Rectangle {
                    visible: org.active
                    width: 2
                    anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                    color: Theme.accent
                }
                RkFocusFrame { shown: orgList.activeFocus && org.ListView.isCurrentItem; anchors.margins: 0 }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.rowPaddingX
                    anchors.rightMargin: Theme.rowPaddingX
                    spacing: Theme.spaceMd
                    RkText {
                        Layout.fillWidth: true
                        text: org.modelData.login
                        color: org.active ? Theme.accent : Theme.fg
                    }
                    RkText { text: org.modelData.count; role: "small"; muted: true }
                }

                MouseArea {
                    id: orgMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: { orgList.currentIndex = org.index; root.toggleOrg(org.modelData.login) }
                }
            }
        }

        // Links for the organization the list is filtered to.
        Flow {
            id: orgLinks
            readonly property string login: Repos.organizations.some((o) => o.login === Repos.list.owner) ? Repos.list.owner : ""
            Layout.fillWidth: true
            Layout.leftMargin: Theme.rowPaddingX
            Layout.rightMargin: Theme.rowPaddingX
            Layout.topMargin: Theme.spaceSm
            visible: login.length > 0
            spacing: Theme.spaceSm
            RkButton { text: "GitHub"; variant: "ghost"; onClicked: Repos.openUrl(root.orgUrl(orgLinks.login)) }
            RkButton { text: "People"; variant: "ghost"; onClicked: Repos.openUrl(root.orgUrl(orgLinks.login, "people")) }
            RkButton { text: "Settings"; variant: "ghost"; onClicked: Repos.openUrl(root.orgUrl(orgLinks.login, "settings")) }
        }
        // Organizations that restrict third-party apps are invisible until approved.
        RkButton {
            id: missingOrg
            Layout.leftMargin: Theme.rowPaddingX - Theme.spaceSm
            Layout.topMargin: Theme.spaceSm
            variant: "ghost"
            text: "Missing an organization?"
            onClicked: Repos.openUrl(Auth.appAccessUrl)
            Accessible.description: "Opens GitHub's page for granting Repokase access to your organizations"
        }
        RkText {
            Layout.fillWidth: true
            Layout.margins: Theme.rowPaddingX
            text: orgList.count > 0 ? "Enter filter · o open on GitHub"
                : "Organizations appear here once they own a repository you can see. + creates one on GitHub."
            role: "caption"
            muted: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }
    }
}
