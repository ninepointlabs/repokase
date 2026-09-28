import QtQuick
import QtQuick.Templates as T
import Repokase

T.TextField {
    id: control

    // Optional leading label, e.g. "/" as a shortcut hint.
    property string hint: ""

    implicitHeight: Theme.controlHeight
    implicitWidth: 24 * Theme.fontBody
    leftPadding: Theme.controlPaddingX + (hintLabel.visible ? hintLabel.implicitWidth + Theme.spaceMd : 0)
    rightPadding: Theme.controlPaddingX + (clearButton.visible ? clearButton.width : 0)
    verticalAlignment: Text.AlignVCenter

    color: Theme.fg
    placeholderTextColor: Theme.fgMuted
    selectionColor: Theme.selection
    selectedTextColor: Theme.fg
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    selectByMouse: true

    background: Rectangle {
        radius: Theme.radius
        color: Theme.bgInset
        border.width: Theme.borderWidth
        border.color: control.activeFocus ? Theme.focusRing : control.hovered ? Theme.borderStrong : Theme.border

        // Templates.TextField draws no placeholder; styles normally supply one.
        RkText {
            x: control.leftPadding
            width: control.width - control.leftPadding - control.rightPadding
            anchors.verticalCenter: parent.verticalCenter
            visible: control.text.length === 0 && control.preeditText.length === 0
            text: control.placeholderText
            color: control.placeholderTextColor
            font: control.font
        }

        RkText {
            id: hintLabel
            visible: control.hint.length > 0 && control.text.length === 0 && !control.activeFocus
            anchors.left: parent.left
            anchors.leftMargin: Theme.controlPaddingX
            anchors.verticalCenter: parent.verticalCenter
            text: control.hint
            role: "caption"
            muted: true
        }

        Rectangle {
            id: clearButton
            visible: control.text.length > 0
            width: control.height
            height: control.height
            anchors.right: parent.right
            color: clearMouse.containsMouse ? Theme.hoverFill : "transparent"
            radius: Theme.radius
            RkText {
                anchors.centerIn: parent
                text: "×"
                muted: !clearMouse.containsMouse
            }
            MouseArea {
                id: clearMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: { control.clear(); control.forceActiveFocus() }
            }
        }
    }
}
