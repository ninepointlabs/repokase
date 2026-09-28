import QtQuick
import Repokase

// A bordered surface. `level`: sunken (sidebars), base, raised (cards, dialogs).
Rectangle {
    property string level: "sunken"
    property bool bordered: true
    default property alias content: inner.data
    property alias padding: inner.anchors.margins

    color: level === "raised" ? Theme.bgRaised : level === "base" ? Theme.bg : Theme.bgSunken
    radius: Theme.radius
    border.width: bordered ? Theme.borderWidth : 0
    border.color: Theme.border

    Item {
        id: inner
        anchors.fill: parent
        anchors.margins: Theme.panelPadding
    }
}
