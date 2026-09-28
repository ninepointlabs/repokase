import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Repokase

// Modal dialog over a theme scrim. Put body items as children and buttons
// in `buttons`. Esc closes. Open with show(restore): `restore` is a function
// that puts focus back afterwards (delegates may be rebuilt while we're open,
// so a remembered item is only the fallback).
T.Popup {
    id: dialog

    property string title: ""
    property string message: ""
    default property alias body: bodyColumn.data
    property alias buttons: buttonRow.data
    property Item returnFocusTo: null
    property var restoreFocus: null

    function show(restore, fromItem) {
        restoreFocus = typeof restore === "function" ? restore : null
        returnFocusTo = fromItem || null
        open()
    }

    parent: T.Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(parent ? parent.width - 2 * Theme.spaceHuge : 480, 34 * Theme.fontBody)
    // Templates don't size popups; do what the stock styles do.
    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset, contentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset, contentHeight + topPadding + bottomPadding)
    padding: Theme.panelPadding
    modal: true
    focus: true
    closePolicy: T.Popup.CloseOnEscape

    onClosed: {
        if (restoreFocus) restoreFocus()
        else if (returnFocusTo) returnFocusTo.forceActiveFocus(Qt.TabFocusReason)
        restoreFocus = null
        returnFocusTo = null
    }

    T.Overlay.modal: Rectangle { color: Theme.scrim }

    background: Rectangle {
        color: Theme.bgRaised
        radius: Theme.radius
        border.width: Theme.borderWidth
        border.color: Theme.focusRing
    }

    contentItem: ColumnLayout {
        spacing: Theme.spaceXl

        RkText {
            Layout.fillWidth: true
            visible: dialog.title.length > 0
            text: dialog.title
            role: "title"
            font.weight: Font.DemiBold
        }
        RkText {
            Layout.fillWidth: true
            visible: dialog.message.length > 0
            text: dialog.message
            secondary: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }
        ColumnLayout {
            id: bodyColumn
            Layout.fillWidth: true
            spacing: Theme.spaceLg
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            RowLayout {
                id: buttonRow
                spacing: Theme.spaceLg
            }
        }
    }
}
