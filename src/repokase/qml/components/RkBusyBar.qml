import QtQuick
import Repokase

// Indeterminate progress: a sliding accent segment on a hairline track.
Item {
    id: root
    property bool running: true
    implicitHeight: 2
    clip: true
    visible: running

    Rectangle { anchors.fill: parent; color: Theme.border }

    Rectangle {
        id: seg
        width: root.width * 0.3
        height: parent.height
        color: Theme.accent
        NumberAnimation on x {
            from: -seg.width
            to: root.width
            duration: 1200
            loops: Animation.Infinite
            running: root.running && root.visible
        }
    }
}
