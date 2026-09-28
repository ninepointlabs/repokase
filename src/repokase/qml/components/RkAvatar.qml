import QtQuick
import Repokase

// Account avatar with an initial-letter fallback while loading or offline.
Rectangle {
    id: root
    property string source: ""
    property string name: ""
    property int size: Theme.controlHeight

    implicitWidth: size
    implicitHeight: size
    radius: Theme.radius
    color: Theme.bgRaised
    border.width: Theme.borderWidth
    border.color: Theme.border
    clip: true

    RkText {
        anchors.centerIn: parent
        visible: img.status !== Image.Ready
        text: root.name.length ? root.name.charAt(0).toUpperCase() : "?"
        color: Theme.fgSecondary
    }

    Image {
        id: img
        anchors.fill: parent
        anchors.margins: Theme.borderWidth
        source: root.source ? root.source + (root.source.indexOf("?") >= 0 ? "&" : "?") + "s=" + (root.size * 2) : ""
        sourceSize.width: root.size * 2
        sourceSize.height: root.size * 2
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        smooth: true
    }
}
