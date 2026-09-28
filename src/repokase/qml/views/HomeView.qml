import QtQuick
import QtQuick.Layouts
import Repokase
import "../components"

// Signed-in shell: account header over the repository list.
FocusScope {
    id: root
    focus: true
    signal aboutRequested()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ------------------------------------------------------ header
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Theme.controlHeight + 2 * Theme.spaceLg
            color: Theme.bgSunken

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.panelPadding
                anchors.rightMargin: Theme.spaceLg
                spacing: Theme.spaceLg

                RkText { text: App.name; role: "title"; font.weight: Font.Bold; color: Theme.accent }
                Item { Layout.fillWidth: true }

                RkButton {
                    text: Repos.refreshing ? "Refreshing…" : "Refresh"
                    hint: "Ctrl+R"
                    enabled: !Repos.refreshing
                    focusPolicy: Qt.TabFocus
                    onClicked: Repos.refresh()
                }
                RkAvatar { source: Auth.avatarUrl; name: Auth.login; size: Theme.controlHeight }
                ColumnLayout {
                    spacing: 0
                    RkText { text: Auth.displayName.length ? Auth.displayName : Auth.login; role: "small" }
                    RkText { visible: Auth.displayName.length > 0; text: "@" + Auth.login; role: "caption"; muted: true }
                }
                RkButton {
                    variant: "ghost"
                    text: "?"
                    implicitWidth: Theme.controlHeight
                    focusPolicy: Qt.TabFocus
                    onClicked: root.aboutRequested()
                    Accessible.name: "About Repokase and keyboard shortcuts"
                }
                RkButton {
                    id: signOut
                    variant: "ghost"
                    text: "Sign out"
                    onClicked: Auth.signOut()
                }
            }

            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: Theme.borderWidth
                color: Theme.border
            }
        }

        RkNotice { Layout.fillWidth: true; Layout.margins: Theme.spaceLg; kind: "warning"; text: Auth.notice }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Sidebar {
                id: sidebar
                Layout.fillHeight: true
                Layout.preferredWidth: 22 * Theme.fontBody * 0.62 + 2 * Theme.rowPaddingX
                visible: root.showSidebar && !(root.singlePane && root.detailOpen)
                dialogs: dialogs
            }
            RepoListView {
                id: listView
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: !(root.singlePane && root.detailOpen)
                focus: true
                onOpenDetail: root.showDetailPane()
                actions: actionDialogs
            }
            DetailPane {
                id: detailPane
                Layout.fillHeight: true
                Layout.fillWidth: root.singlePane
                Layout.preferredWidth: root.singlePane ? -1
                    : Math.max(26 * Theme.fontBody, Math.min(40 * Theme.fontBody, root.width * 0.34))
                visible: root.singlePane ? root.detailOpen : root.detailBeside
                showBack: root.singlePane
                dialogs: dialogs
                actions: actionDialogs
                onCopied: (what) => listView.showFlash("Copied " + what)
                onBack: root.backToList()
            }
        }
    }

    // Layout adapts to the window: Omarchy tiles windows to half a screen, so
    // narrow is the common case, not an edge case.
    //   >= 1180px  sidebar | list | details
    //   >=  900px  list | details
    //    <  900px  list, or details full-width (Enter / double-click; Esc back)
    // Ctrl+B / Ctrl+I override the automatic choice.
    property var sidebarPref: undefined
    property var detailPref: undefined
    property bool detailOpen: false
    readonly property bool singlePane: width < 900 || detailPref === false
    readonly property bool showSidebar: sidebarPref === undefined ? width >= 1180 : sidebarPref
    readonly property bool detailBeside: !singlePane

    function showDetailPane() {
        if (singlePane) detailOpen = true
        detailPane.focusFirst()
    }
    function backToList() {
        detailOpen = false
        listView.focusList()
    }

    Shortcut { sequence: "Ctrl+B"; onActivated: root.sidebarPref = !root.showSidebar }
    Shortcut {
        sequence: "Ctrl+I"
        onActivated: {
            if (root.width < 900) { root.detailOpen ? root.backToList() : root.showDetailPane() }
            else root.detailPref = root.detailPref === false ? undefined : false
        }
    }
    Shortcut { sequence: "Ctrl+1"; onActivated: { root.sidebarPref = true; root.detailOpen = false; sidebar.focusList() } }
    Shortcut { sequence: "Ctrl+2"; onActivated: root.backToList() }
    Shortcut { sequence: "o"; enabled: root.detailOpen && Detail.hasRepo; onActivated: Repos.openUrl(Detail.link("repo")) }

    CategoryDialogs { id: dialogs }
    ActionDialogs {
        id: actionDialogs
        restoreFocus: () => (root.singlePane && root.detailOpen) ? detailPane.focusFirst() : listView.focusList()
        onFlash: (text) => listView.showFlash(text)
    }
    Connections {
        target: Actions
        function onDone(message) { listView.showFlash(message) }
        function onDeleted(nodeId) { if (root.detailOpen) root.backToList() }
    }
    Connections {
        target: Workflows
        function onDone(message) { listView.showFlash(message) }
    }
}
