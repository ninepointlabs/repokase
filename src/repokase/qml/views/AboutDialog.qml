import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Repokase
import "../components"

// About Repokase + keyboard reference. F1 or ? opens it.
RkDialog {
    id: dialog
    width: Math.min(parent ? parent.width - 2 * Theme.spaceHuge : 640, 58 * Theme.fontBody)
    onOpened: closeButton.forceActiveFocus(Qt.TabFocusReason)

    readonly property var shortcuts: [
        ["Anywhere", ""],
        ["/  Ctrl+F", "Search"],
        ["Ctrl+R  F5", "Refresh from GitHub"],
        ["Ctrl+1 / Ctrl+2", "Focus categories / list"],
        ["Ctrl+B / Ctrl+I", "Toggle side panes"],
        ["F1  ?", "This help"],
        ["Ctrl+Q", "Quit"],
        ["Repository list", ""],
        ["j k  ↑ ↓", "Move"],
        ["g G  Home End", "First / last"],
        ["Enter  l  →", "Details"],
        ["o", "Open on GitHub"],
        ["c", "Copy URL"],
        ["1 … 9", "Toggle category"],
        ["e", "Edit description"],
        ["Shift+A / Shift+V", "Archive / visibility"],
        ["Delete", "Delete (type name to confirm)"],
        ["x  Space", "Mark for bulk actions"],
        ["Shift+↓ ↑  Ctrl+A", "Extend marks / mark all"],
        ["Esc", "Clear marks / search / go back"],
        ["Categories", ""],
        ["n  F2  Delete", "New / rename / remove"],
        ["Alt+↑ ↓", "Reorder"],
    ]

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.spaceXs
        RowLayout {
            spacing: Theme.spaceLg
            Image {
                source: "../../assets/repokase.svg"
                sourceSize.width: Theme.fontDisplay * 2
                sourceSize.height: Theme.fontDisplay * 2
                Layout.preferredWidth: Theme.fontDisplay * 2
                Layout.preferredHeight: Theme.fontDisplay * 2
            }
            ColumnLayout {
                spacing: Theme.spaceXxs
                RkText { text: App.name; role: "display"; font.weight: Font.Bold; color: Theme.accent }
                RkText { text: App.tagline; secondary: true }
                RkText { text: "Version " + App.version + " · Qt " + App.qtVersion + " · MIT License"; role: "caption"; muted: true }
            }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: 2
        columnSpacing: Theme.spaceXl
        rowSpacing: Theme.spaceXs
        RkText { text: "Account"; role: "small"; muted: true }
        RkText { Layout.fillWidth: true; text: Auth.login ? "@" + Auth.login : "Not signed in"; role: "small" }
        RkText { text: "Permissions"; role: "small"; muted: true }
        RkText { Layout.fillWidth: true; text: Auth.scopes || "—"; role: "small" }
        RkText { text: "Theme"; role: "small"; muted: true }
        RkText { Layout.fillWidth: true; text: Theme.name + (Theme.source === "fallback" ? " (built-in fallback)" : " (follows Omarchy)") + " · " + Theme.fontFamily; role: "small" }
        RkText { text: "Data"; role: "small"; muted: true }
        RkText { Layout.fillWidth: true; text: App.dataDir + " · token in your keyring"; role: "small"; elide: Text.ElideMiddle }
    }

    Rectangle { Layout.fillWidth: true; height: Theme.borderWidth; color: Theme.border }

    Flow {
        Layout.fillWidth: true
        spacing: Theme.spaceXl
        Repeater {
            model: dialog.shortcuts
            RowLayout {
                required property var modelData
                width: modelData[1] === "" ? dialog.availableWidth : (dialog.availableWidth - Theme.spaceXl) / 2
                spacing: Theme.spaceMd
                RkText {
                    visible: modelData[1] === ""
                    Layout.topMargin: Theme.spaceSm
                    text: modelData[0].toUpperCase()
                    role: "caption"
                    muted: true
                    font.letterSpacing: 1
                }
                RkText {
                    visible: modelData[1] !== ""
                    Layout.preferredWidth: 18 * Theme.fontSmall * 0.62
                    Layout.alignment: Qt.AlignTop
                    text: modelData[0]
                    role: "small"
                    color: Theme.accent
                }
                RkText {
                    visible: modelData[1] !== ""
                    Layout.fillWidth: true
                    text: modelData[1]
                    role: "small"
                    secondary: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                }
            }
        }
    }

    buttons: [
        RkButton { text: "Project page"; onClicked: Repos.openUrl(App.homepage) },
        RkButton { id: closeButton; text: "Close"; variant: "primary"; hint: "Esc"; onClicked: dialog.close() }
    ]
}
