import QtQuick
import Repokase

// Inline message strip. kind: info | warning | danger | success
Rectangle {
    id: root
    property string kind: "info"
    property alias text: label.text
    readonly property color tone: kind === "danger" ? Theme.danger
        : kind === "warning" ? Theme.warning
        : kind === "success" ? Theme.success
        : Theme.info

    visible: text.length > 0
    implicitHeight: label.implicitHeight + 2 * Theme.spaceLg
    radius: Theme.radius
    color: Theme.tint(tone, 0.12)
    border.width: Theme.borderWidth
    border.color: Theme.tint(tone, 0.5)

    Rectangle {
        width: 3
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        color: root.tone
    }

    RkText {
        id: label
        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
        anchors.leftMargin: Theme.spaceXl + 3
        anchors.rightMargin: Theme.spaceXl
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
    }
}
