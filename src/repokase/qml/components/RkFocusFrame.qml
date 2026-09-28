import QtQuick
import Repokase

// Keyboard focus indicator, matching Hyprland's active-border color.
// Drop inside any focusable item. Bind `shown` to activeFocus unless the
// focus came from a mouse click (window activation resets visualFocus).
Rectangle {
    property bool shown: false
    // Gap between control and ring, so the ring reads even on accent fills.
    readonly property int gap: 2
    anchors.fill: parent
    anchors.margins: -(Theme.focusWidth + gap)
    color: "transparent"
    radius: Theme.radius > 0 ? Theme.radius + Theme.focusWidth + gap : 0
    border.width: Theme.focusWidth
    border.color: Theme.focusRing
    visible: shown
    z: 10
}
