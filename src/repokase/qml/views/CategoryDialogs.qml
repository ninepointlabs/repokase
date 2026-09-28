import QtQuick
import QtQuick.Layouts
import Repokase
import "../components"

// Create / rename / delete dialogs for local categories.
Item {
    id: root

    // `restore` (optional) re-focuses the caller once the dialog closes.
    function create(restore) { nameDialog.open_("create", -1, "", restore) }
    function rename(id, name, restore) { nameDialog.open_("rename", id, name, restore) }
    function remove(id, name, count, restore) {
        deleteDialog.categoryId = id
        deleteDialog.message = 'Delete "' + name + '"? '
            + (count > 0 ? count + " repo" + (count === 1 ? " loses" : "s lose") + " this category. " : "")
            + "Repositories on GitHub are not affected."
        deleteDialog.show(restore, root.Window.activeFocusItem)
    }

    RkDialog {
        id: nameDialog
        property string mode: "create"
        property int categoryId: -1
        property string error: ""

        function open_(m, id, name, restore) {
            mode = m; categoryId = id; error = ""
            field.text = name
            show(restore, root.Window.activeFocusItem)
            field.forceActiveFocus(Qt.TabFocusReason)
            field.selectAll()
        }
        function submit() {
            error = mode === "create" ? Repos.createCategory(field.text) : Repos.renameCategory(categoryId, field.text)
            if (!error.length) close()
        }

        title: mode === "create" ? "New category" : "Rename category"
        message: mode === "create" ? "Categories are local to this computer and never sent to GitHub." : ""

        RkTextField {
            id: field
            Layout.fillWidth: true
            placeholderText: "e.g. Work, Plugins, Archive candidates"
            maximumLength: 40
            onAccepted: nameDialog.submit()
            onTextEdited: nameDialog.error = ""
        }
        RkNotice { Layout.fillWidth: true; kind: "danger"; text: nameDialog.error }

        buttons: [
            RkButton { text: "Cancel"; variant: "ghost"; hint: "Esc"; onClicked: nameDialog.close() },
            RkButton {
                text: nameDialog.mode === "create" ? "Create" : "Rename"
                variant: "primary"
                hint: "Enter"
                enabled: field.text.trim().length > 0
                onClicked: nameDialog.submit()
            }
        ]
    }

    RkDialog {
        id: deleteDialog
        property int categoryId: -1
        title: "Delete category"
        onOpened: cancelButton.forceActiveFocus(Qt.TabFocusReason)

        buttons: [
            RkButton { id: cancelButton; text: "Cancel"; variant: "ghost"; hint: "Esc"; onClicked: deleteDialog.close() },
            RkButton {
                text: "Delete"
                variant: "danger"
                onClicked: { Repos.deleteCategory(deleteDialog.categoryId); deleteDialog.close() }
            }
        ]
    }
}
