import QtQuick
import QtQuick.Templates as T
import Repokase

T.ScrollBar {
    id: control
    implicitWidth: Theme.spaceMd + 2
    implicitHeight: Theme.spaceMd + 2
    padding: 1
    minimumSize: 0.05
    visible: size < 1.0
    policy: T.ScrollBar.AsNeeded

    contentItem: Rectangle {
        radius: Theme.radius > 0 ? width / 2 : 0
        color: control.pressed ? Theme.fgSecondary : control.hovered ? Theme.fgMuted : Theme.borderStrong
        opacity: control.active || control.hovered ? 1 : 0.6
        Behavior on opacity { NumberAnimation { duration: 150 } }
    }
}
