import QtQuick
import QtQuick.Templates as T
import Repokase

// Compact pill for topics and categories.
//   toggle chip:    checkable: true, bind `checked`, handle clicked()
//   removable chip: removable: true, handle removed() (click ×, Delete or Backspace)
T.AbstractButton {
    id: chip

    property bool removable: false
    property color tone: Theme.fgSecondary
    property bool showDot: false
    signal removed()

    checkable: false
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true
    implicitHeight: Math.round(Theme.controlHeight * 0.85)
    implicitWidth: row.implicitWidth + 2 * Theme.spaceLg
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    Keys.onDeletePressed: if (removable) removed()
    Keys.onPressed: (e) => { if (e.key === Qt.Key_Backspace && removable) { removed(); e.accepted = true } }

    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: Theme.spaceSm
            Rectangle {
                visible: chip.showDot
                anchors.verticalCenter: parent.verticalCenter
                width: Theme.spaceMd; height: width
                radius: Theme.radius > 0 ? width / 2 : 0
                color: chip.tone
            }
            RkText {
                anchors.verticalCenter: parent.verticalCenter
                text: chip.text
                role: "small"
                color: chip.checked ? Theme.fg : chip.showDot ? Theme.fgSecondary : chip.tone
            }
            RkText {
                visible: chip.removable
                anchors.verticalCenter: parent.verticalCenter
                text: "×"
                role: "small"
                color: removeMouse.containsMouse ? Theme.danger : Theme.fgMuted
                MouseArea {
                    id: removeMouse
                    anchors.fill: parent
                    anchors.margins: -Theme.spaceSm
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: chip.removed()
                }
            }
        }
    }

    background: Rectangle {
        radius: Theme.radius > 0 ? height / 2 : 0
        color: chip.checked ? Theme.tint(chip.tone, 0.22)
            : chip.down ? Theme.pressedFill
            : chip.hovered ? Theme.hoverFill
            : "transparent"
        border.width: Theme.borderWidth
        border.color: chip.checked ? chip.tone : Theme.border
        RkFocusFrame { shown: chip.activeFocus && chip.focusReason !== Qt.MouseFocusReason }
    }
}
