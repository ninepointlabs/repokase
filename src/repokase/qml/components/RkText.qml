import QtQuick
import Repokase

// Themed text. Use `role` for the type scale instead of raw pixel sizes.
Text {
    property string role: "body" // caption, small, body, subtitle, title, heading, display
    property bool muted: false
    property bool secondary: false

    color: muted ? Theme.fgMuted : secondary ? Theme.fgSecondary : Theme.fg
    font.family: Theme.fontFamily
    font.pixelSize: role === "caption" ? Theme.fontCaption
        : role === "small" ? Theme.fontSmall
        : role === "subtitle" ? Theme.fontSubtitle
        : role === "title" ? Theme.fontTitle
        : role === "heading" ? Theme.fontHeading
        : role === "display" ? Theme.fontDisplay
        : Theme.fontBody
    linkColor: Theme.accent
    elide: Text.ElideRight
    textFormat: Text.PlainText
}
