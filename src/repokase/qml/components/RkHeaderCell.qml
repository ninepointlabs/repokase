import QtQuick
import QtQuick.Templates as T
import Repokase

// Sortable column header. Shows an arrow when it is the active sort key.
T.AbstractButton {
    id: control
    property string key: ""
    property string activeKey: ""
    property bool descending: false
    property int align: Text.AlignRight
    readonly property bool active: key === activeKey

    implicitHeight: Theme.controlHeight
    focusPolicy: Qt.TabFocus
    hoverEnabled: true
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()

    contentItem: RkText {
        text: control.text + (control.active ? (control.descending ? " ↓" : " ↑") : "")
        role: "small"
        horizontalAlignment: control.align
        verticalAlignment: Text.AlignVCenter
        color: control.active ? Theme.accent : control.hovered ? Theme.fg : Theme.fgMuted
        font.weight: control.active ? Font.DemiBold : Font.Normal
    }

    background: Item {
        RkFocusFrame { shown: control.activeFocus; anchors.margins: 0 }
    }
}
