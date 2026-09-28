import QtQuick
import QtQuick.Templates as T
import Repokase

T.Button {
    id: control

    // secondary | primary | danger | ghost
    property string variant: "secondary"
    // Optional key hint rendered after the label, e.g. "Enter".
    property string hint: ""

    // Disabled primary/danger buttons fall back to the neutral look: muted
    // text on an accent fill is unreadable.
    readonly property bool filled: enabled && (variant === "primary" || variant === "danger")
    readonly property color baseFill: !filled ? "transparent"
        : variant === "primary" ? Theme.accent
        : Theme.danger
    readonly property color textColor: !enabled ? Theme.fgMuted
        : filled ? Theme.accentFg
        : variant === "ghost" ? Theme.fgSecondary
        : Theme.fg

    implicitHeight: Theme.controlHeight
    implicitWidth: Math.max(implicitHeight, implicitContentWidth + leftPadding + rightPadding)
    topPadding: 0
    bottomPadding: 0
    leftPadding: Theme.controlPaddingX
    rightPadding: Theme.controlPaddingX
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true
    opacity: enabled ? 1 : 0.55

    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight

        Row {
            id: row
            anchors.centerIn: parent
            spacing: Theme.spaceMd
            RkText {
                anchors.verticalCenter: parent.verticalCenter
                text: control.text
                color: control.textColor
                font.weight: control.filled ? Font.DemiBold : Font.Normal
            }
            RkText {
                visible: control.hint.length > 0
                anchors.verticalCenter: parent.verticalCenter
                text: control.hint
                role: "caption"
                color: control.textColor
                opacity: 0.7
            }
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: control.baseFill
        border.width: control.filled || control.variant === "ghost" ? 0 : Theme.borderWidth
        border.color: control.hovered ? Theme.borderStrong : Theme.border

        // State overlay: same hover/press alphas as the Omarchy shell.
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: control.down ? (control.filled ? Theme.tint(Theme.accentFg, 0.18) : Theme.pressedFill)
                : control.hovered ? (control.filled ? Theme.tint(Theme.accentFg, 0.10) : Theme.hoverFill)
                : !control.filled && control.variant !== "ghost" ? Theme.normalFill
                : "transparent"
        }

        RkFocusFrame { shown: control.activeFocus && control.focusReason !== Qt.MouseFocusReason }
    }
}
