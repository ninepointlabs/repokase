import QtQuick
import QtQuick.Layouts
import Repokase
import "../components"

// Shown instead of everything else when the cache can't be opened or written.
FocusScope {
    id: root
    focus: true

    Component.onCompleted: quitButton.forceActiveFocus(Qt.TabFocusReason)

    RkPane {
        level: "sunken"
        anchors.centerIn: parent
        width: Math.min(parent.width - 2 * Theme.spaceHuge, 36 * Theme.fontBody + 2 * Theme.panelPadding)
        height: body.implicitHeight + 2 * Theme.panelPadding
        padding: Theme.panelPadding

        ColumnLayout {
            id: body
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: Theme.spaceXxl

            RkText { text: App.name; role: "display"; font.weight: Font.Bold; color: Theme.accent }
            RkNotice { Layout.fillWidth: true; kind: "danger"; text: App.cacheError }
            RkButton {
                id: quitButton
                Layout.alignment: Qt.AlignRight
                variant: "primary"
                text: "Quit"
                hint: "Ctrl+Q"
                onClicked: Qt.quit()
            }
        }
    }
}
