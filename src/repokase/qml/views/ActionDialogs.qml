import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Repokase
import "../components"

// Dialogs for repository actions. Entry points take a repo node id:
//   editDescription(id)  toggleArchive(id)  changeVisibility(id)  remove(id)
// `flash(text)` is called for "can't do that" messages.
Item {
    id: root
    signal flash(string text)
    property var restoreFocus: null

    function repoOf(id) { return Repos.repo(id) }
    function caps(id) { return Actions.capabilities(id) }
    function focusBack() { if (restoreFocus) restoreFocus() }

    function editDescription(id) {
        const c = caps(id)
        if (!c.description) { flash(c.descriptionWhy); return }
        const r = repoOf(id)
        descDialog.nodeId = id
        descDialog.title = "Description · " + r.full_name
        descField.text = r.description || ""
        descDialog.show(focusBack)
        descField.forceActiveFocus(Qt.TabFocusReason)
        descField.selectAll()
    }
    function toggleArchive(id) {
        const c = caps(id)
        if (!c.archive) { flash(c.archiveWhy); return }
        const r = repoOf(id)
        archiveDialog.nodeId = id
        archiveDialog.archive = !r.is_archived
        archiveDialog.show(focusBack)
    }
    function changeVisibility(id) {
        const c = caps(id)
        if (!c.visibility) { flash(c.visibilityWhy); return }
        const r = repoOf(id)
        visDialog.nodeId = id
        visDialog.current = r.visibility.toLowerCase()
        visDialog.target = visDialog.current === "public" ? "private" : "public"
        visDialog.canInternal = c.canInternal
        visDialog.show(focusBack)
    }
    function bulkArchive(archived) {
        const ids = Repos.markedIds
        if (!ids.length) return
        bulkDialog.ids = ids
        bulkDialog.archive = archived
        bulkDialog.show(focusBack)
    }
    function remove(id) {
        const c = caps(id)
        if (!c.delete) { flash(c.deleteWhy); return }
        if (!c.hasDeleteScope) {
            reauthDialog.nodeId = id
            reauthDialog.show(null)
            return
        }
        const r = repoOf(id)
        deleteDialog.nodeId = id
        deleteDialog.fullName = r.full_name
        deleteField.text = ""
        deleteDialog.show(focusBack)
        deleteField.forceActiveFocus(Qt.TabFocusReason)
    }

    // ---------------------------------------------------------- description
    RkDialog {
        id: descDialog
        property string nodeId: ""
        function submit() { Actions.setDescription(nodeId, descField.text); close() }

        RkTextField {
            id: descField
            Layout.fillWidth: true
            placeholderText: "What is this repository about?"
            maximumLength: Actions.descriptionMax
            onAccepted: descDialog.submit()
        }
        RkText {
            Layout.alignment: Qt.AlignRight
            text: descField.text.length + " / " + Actions.descriptionMax
            role: "caption"
            color: descField.text.length > Actions.descriptionMax - 20 ? Theme.warning : Theme.fgMuted
        }
        buttons: [
            RkButton { text: "Cancel"; variant: "ghost"; hint: "Esc"; onClicked: descDialog.close() },
            RkButton { text: "Save"; variant: "primary"; hint: "Enter"; onClicked: descDialog.submit() }
        ]
    }

    // -------------------------------------------------------------- archive
    RkDialog {
        id: archiveDialog
        property string nodeId: ""
        property bool archive: true
        title: (archive ? "Archive " : "Unarchive ") + (root.repoOf(nodeId) || {}).full_name
        message: archive
            ? "The repository becomes read-only: no pushes, issues, pull requests or comments. "
              + "You can unarchive it at any time."
            : "The repository becomes writable again for everyone with access."
        // Hard-to-reverse changes open on Cancel: Tab, then Enter, to confirm.
        onOpened: archiveCancel.forceActiveFocus(Qt.TabFocusReason)
        buttons: [
            RkButton { id: archiveCancel; text: "Cancel"; variant: "ghost"; hint: "Esc"; onClicked: archiveDialog.close() },
            RkButton {
                text: archiveDialog.archive ? "Archive" : "Unarchive"
                variant: archiveDialog.archive ? "danger" : "primary"
                onClicked: { Actions.setArchived(archiveDialog.nodeId, archiveDialog.archive); archiveDialog.close() }
            }
        ]
    }

    // ----------------------------------------------------------- visibility
    RkDialog {
        id: visDialog
        property string nodeId: ""
        property string current: "public"
        property string target: "private"
        property bool canInternal: false
        title: "Change visibility · " + ((root.repoOf(nodeId) || {}).full_name || "")
        message: target === "private"
            ? "Only you and people you grant access will see it. GitHub removes stars and watchers "
              + "from people without access, and existing public forks stay public but detached."
            : target === "public"
            ? "Everyone on the internet will be able to see the code, full history, issues and releases. "
              + "Check the history for secrets before continuing."
            : "Everyone in your enterprise will be able to see it."
        onOpened: visCancel.forceActiveFocus(Qt.TabFocusReason)

        RowLayout {
            visible: visDialog.canInternal // only a real choice for internal repos
            spacing: Theme.spaceMd
            Repeater {
                model: ["public", "private"].concat(visDialog.canInternal ? ["internal"] : [])
                RkChip {
                    required property string modelData
                    visible: modelData !== visDialog.current
                    text: "Make " + modelData
                    checked: visDialog.target === modelData
                    tone: modelData === "public" ? Theme.warning : Theme.info
                    onClicked: visDialog.target = modelData
                }
            }
        }
        buttons: [
            RkButton { id: visCancel; text: "Cancel"; variant: "ghost"; hint: "Esc"; onClicked: visDialog.close() },
            RkButton {
                text: "Make " + visDialog.target
                variant: visDialog.target === "public" ? "danger" : "primary"
                onClicked: { Actions.setVisibility(visDialog.nodeId, visDialog.target); visDialog.close() }
            }
        ]
    }

    // ----------------------------------------------------------- bulk archive
    RkDialog {
        id: bulkDialog
        property var ids: []
        property bool archive: true
        readonly property var names: ids.map((id) => Repos.repo(id).full_name || id)
        title: (archive ? "Archive " : "Unarchive ") + ids.length + " repositor" + (ids.length === 1 ? "y" : "ies")
        message: archive
            ? "Each becomes read-only (no pushes, issues, pull requests or comments). Repositories you don't administer, or that are already archived, are skipped."
            : "Each becomes writable again. Repositories you don't administer, or that aren't archived, are skipped."
        onOpened: bulkCancel.forceActiveFocus(Qt.TabFocusReason)

        RkText {
            Layout.fillWidth: true
            text: bulkDialog.names.slice(0, 12).join("\n") + (bulkDialog.names.length > 12 ? "\n… and " + (bulkDialog.names.length - 12) + " more" : "")
            role: "small"
            secondary: true
            wrapMode: Text.WrapAnywhere
            elide: Text.ElideNone
        }
        buttons: [
            RkButton { id: bulkCancel; text: "Cancel"; variant: "ghost"; hint: "Esc"; onClicked: bulkDialog.close() },
            RkButton {
                text: (bulkDialog.archive ? "Archive " : "Unarchive ") + bulkDialog.ids.length
                variant: bulkDialog.archive ? "danger" : "primary"
                onClicked: { Actions.bulkArchive(bulkDialog.ids, bulkDialog.archive); bulkDialog.close() }
            }
        ]
    }

    // --------------------------------------------------------------- delete
    RkDialog {
        id: deleteDialog
        property string nodeId: ""
        property string fullName: ""
        readonly property bool matches: deleteField.text.trim() === fullName
        title: "Delete " + fullName
        message: "This permanently deletes the repository, its wiki, issues, pull requests, releases and "
            + "settings on GitHub. It cannot be undone from Repokase."
        function submit() {
            if (!matches) return
            Actions.deleteRepo(nodeId, deleteField.text)
            close()
        }

        RkText {
            Layout.fillWidth: true
            text: "Type " + deleteDialog.fullName + " to confirm:"
            wrapMode: Text.WrapAnywhere
            elide: Text.ElideNone
        }
        RkTextField {
            id: deleteField
            Layout.fillWidth: true
            placeholderText: deleteDialog.fullName
            onAccepted: deleteDialog.submit()
            Accessible.name: "Type the repository name to confirm deletion"
        }
        buttons: [
            RkButton { text: "Cancel"; variant: "ghost"; hint: "Esc"; onClicked: deleteDialog.close() },
            RkButton {
                text: "Delete this repository"
                variant: "danger"
                enabled: deleteDialog.matches
                onClicked: deleteDialog.submit()
            }
        ]
    }

    // ------------------------------------------------------- re-authorize
    RkDialog {
        id: reauthDialog
        property string nodeId: ""
        readonly property string st: Auth.reauthState
        title: "Allow Repokase to delete repositories"
        message: "You signed in without the delete_repo permission, so Repokase can't delete anything yet. "
            + "GitHub will ask you to approve this one extra permission. Repokase only uses it when you "
            + "confirm a delete by typing the repository's name."
        closePolicy: T.Popup.CloseOnEscape
        onOpened: { reauthStart.forceActiveFocus(Qt.TabFocusReason) }
        onClosed: { if (Auth.reauthState !== "") Auth.cancelReauth(); root.focusBack() }

        Connections {
            target: Auth
            function onReauthorized() {
                const id = reauthDialog.nodeId
                reauthDialog.close()
                root.flash("delete_repo granted")
                Qt.callLater(() => root.remove(id))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: reauthDialog.st === "awaitingUser"
            spacing: Theme.spaceLg
            RkText { text: "Enter this code at " + Auth.verificationUri.replace("https://", ""); secondary: true }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: codeText.implicitHeight + 2 * Theme.spaceLg
                color: Theme.bgInset
                border.width: Theme.borderWidth
                border.color: Theme.border
                radius: Theme.radius
                RkText {
                    id: codeText
                    anchors.centerIn: parent
                    text: Auth.userCode
                    role: "heading"
                    font.weight: Font.Bold
                    font.letterSpacing: Theme.spaceSm
                }
            }
            RowLayout {
                spacing: Theme.spaceLg
                RkButton { id: reauthOpen; text: "Open browser"; variant: "primary"; onClicked: Auth.openBrowser() }
                RkButton { text: "Copy code"; onClicked: Auth.copyCode() }
                RkBusyBar { Layout.fillWidth: true; running: reauthDialog.st === "awaitingUser" }
            }
        }
        RkBusyBar { Layout.fillWidth: true; running: reauthDialog.st === "requesting" }
        RkNotice { Layout.fillWidth: true; kind: "danger"; text: Auth.reauthError }

        onStChanged: if (st === "awaitingUser") reauthOpen.forceActiveFocus(Qt.TabFocusReason)

        buttons: [
            RkButton { text: "Cancel"; variant: "ghost"; hint: "Esc"; onClicked: reauthDialog.close() },
            RkButton {
                id: reauthStart
                visible: reauthDialog.st === "" || reauthDialog.st === "error"
                text: reauthDialog.st === "error" ? "Try again" : "Authorize on GitHub"
                variant: "primary"
                onClicked: Auth.requestScope("delete_repo", "")
            }
        ]
    }
}
