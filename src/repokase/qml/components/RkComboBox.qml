import QtQuick
import QtQuick.Templates as T
import Repokase

// Themed dropdown. model: [{ text, value }, ...]; bind `current` for the
// selected value and handle `picked(value)`.
T.ComboBox {
    id: control

    property string label: ""
    // Accent the value when it differs from the first (default) entry, so
    // active filters stand out. Off for pickers like sort order.
    property bool accentNonDefault: true
    property var current
    signal picked(var value)

    textRole: "text"
    valueRole: "value"
    currentIndex: {
        const m = model || []
        for (let i = 0; i < m.length; i++) if (m[i].value === current) return i
        return 0
    }
    onActivated: (index) => picked(model[index].value)

    implicitHeight: Theme.controlHeight
    implicitWidth: Math.max(8 * Theme.fontBody, implicitContentWidth + leftPadding + rightPadding)
    leftPadding: Theme.controlPaddingX
    rightPadding: Theme.controlPaddingX + indicator.width
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody

    contentItem: Row {
        spacing: Theme.spaceMd
        RkText {
            visible: control.label.length > 0
            anchors.verticalCenter: parent.verticalCenter
            text: control.label
            muted: true
        }
        RkText {
            anchors.verticalCenter: parent.verticalCenter
            text: control.displayText
            color: control.accentNonDefault && control.currentIndex > 0 ? Theme.accent : Theme.fg
        }
    }

    indicator: RkText {
        x: control.width - width - Theme.controlPaddingX
        anchors.verticalCenter: parent.verticalCenter
        text: control.popup.visible ? "▴" : "▾"
        muted: true
    }

    background: Rectangle {
        radius: Theme.radius
        color: control.down || control.popup.visible ? Theme.pressedFill : control.hovered ? Theme.hoverFill : Theme.normalFill
        border.width: Theme.borderWidth
        border.color: control.hovered ? Theme.borderStrong : Theme.border
        RkFocusFrame { shown: control.activeFocus && control.focusReason !== Qt.MouseFocusReason && !control.popup.visible }
    }

    delegate: T.ItemDelegate {
        id: item
        required property var modelData
        required property int index
        width: ListView.view.width
        implicitHeight: Theme.controlHeight
        leftPadding: Theme.controlPaddingX
        rightPadding: Theme.controlPaddingX
        highlighted: control.highlightedIndex === index
        hoverEnabled: true
        contentItem: RkText {
            text: item.modelData.text
            color: control.currentIndex === item.index ? Theme.accent : Theme.fg
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            color: item.highlighted || item.hovered ? Theme.hoverFill : "transparent"
        }
    }

    popup: T.Popup {
        y: control.height + Theme.spaceXs
        width: Math.max(control.width, 14 * Theme.fontBody)
        implicitHeight: Math.min(contentItem.implicitHeight + 2 * padding, 18 * Theme.controlHeight)
        padding: Theme.spaceXs

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.delegateModel
            currentIndex: control.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            T.ScrollBar.vertical: RkScrollBar {}
        }

        background: Rectangle {
            color: Theme.bgRaised
            radius: Theme.radius
            border.width: Theme.borderWidth
            border.color: Theme.focusRing
        }
    }
}
