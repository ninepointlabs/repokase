import QtQuick
import Repokase

// Small outlined label: visibility, archived, fork, topics.
Rectangle {
    id: root
    property alias text: label.text
    property color tone: Theme.fgMuted
    property bool filled: false

    implicitWidth: label.implicitWidth + 2 * Theme.spaceMd
    implicitHeight: label.implicitHeight + Theme.spaceXxs * 2
    radius: Theme.radius
    color: filled ? Theme.tint(tone, 0.16) : "transparent"
    border.width: Theme.borderWidth
    border.color: Theme.tint(tone, 0.6)

    RkText {
        id: label
        anchors.centerIn: parent
        role: "caption"
        color: root.tone
    }
}
