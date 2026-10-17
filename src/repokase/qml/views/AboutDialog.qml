import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Repokase
import "../components"

// About Repokase + keyboard reference. F1 or ? opens it.
RkDialog {
    id: dialog
    objectName: "aboutDialog"
    width: Math.min(parent ? parent.width - 2 * Theme.spaceHuge : 640, 58 * Theme.fontBody)
    onOpened: {
        showLicense = false
        closeButton.forceActiveFocus(Qt.TabFocusReason)
    }

    // The license text takes the shortcut list's place while it's shown.
    property bool showLicense: false

    readonly property var shortcuts: [
        ["Anywhere", ""],
        ["/  Ctrl+F", "Search"],
        ["Ctrl+R  F5", "Refresh from GitHub"],
        ["Ctrl+1 / Ctrl+2", "Focus categories / list"],
        ["Ctrl+B / Ctrl+I", "Toggle side panes"],
        ["F1  ?", "About and shortcuts (this)"],
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
        ["Shift+T", "Transfer to another owner"],
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
                source: App.icon
                sourceSize.width: Theme.fontDisplay * 2
                sourceSize.height: Theme.fontDisplay * 2
                Layout.preferredWidth: Theme.fontDisplay * 2
                Layout.preferredHeight: Theme.fontDisplay * 2
            }
            ColumnLayout {
                spacing: Theme.spaceXxs
                RkText { text: App.name; role: "display"; font.weight: Font.Bold; color: Theme.accent }
                RkText { text: App.tagline; secondary: true }
                RkText { text: "Version " + App.version; role: "caption"; muted: true }
            }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: 2
        columnSpacing: Theme.spaceXl
        rowSpacing: Theme.spaceXs
        RkText { text: "Made by"; role: "small"; muted: true }
        RkText { Layout.fillWidth: true; text: App.organization; role: "small" }
        RkText { text: "Created"; role: "small"; muted: true }
        RkText { Layout.fillWidth: true; text: App.created; role: "small" }
        RkText { text: "License"; role: "small"; muted: true; Layout.alignment: Qt.AlignVCenter }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceLg
            RkText { text: App.license + ", " + App.copyright; role: "small" }
            RkButton {
                objectName: "aboutLicense"
                text: dialog.showLicense ? "Hide" : "Read it"
                variant: "ghost"
                onClicked: dialog.showLicense = !dialog.showLicense
            }
        }
        RkText { text: "Support"; role: "small"; muted: true; Layout.alignment: Qt.AlignVCenter }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceLg
            RkText { text: App.supportEmail; role: "small" }
            RkButton {
                text: "Email"
                variant: "ghost"
                onClicked: Qt.openUrlExternally("mailto:" + App.supportEmail + "?subject="
                    + encodeURIComponent(App.name + " " + App.version) + "&body="
                    + encodeURIComponent("\n\n--\n" + App.details))
            }
            RkButton {
                text: "Copy"
                variant: "ghost"
                onClicked: App.copy(App.supportEmail)
            }
        }
        RkText { text: "Privacy"; role: "small"; muted: true; Layout.alignment: Qt.AlignTop }
        RkText {
            Layout.fillWidth: true
            text: "No telemetry, and no Nine Point Labs account or server. Repokase talks only to GitHub "
                + "(github.com, api.github.com and your avatar image), with the token you approved; that "
                + "token stays in your system keyring. Your repository list, categories and traffic history "
                + "are kept in a local database in your data folder."
            role: "small"
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }
        RkText { text: "Built with"; role: "small"; muted: true }
        RkText {
            Layout.fillWidth: true
            text: "Qt " + App.qtVersion + ", PySide6 " + App.pysideVersion + ", Python " + App.pythonVersion
            role: "small"
            secondary: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }
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

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 14 * Theme.fontSmall
        visible: dialog.showLicense
        color: Theme.bgSunken
        radius: Theme.radius
        border.width: Theme.borderWidth
        border.color: Theme.border
        Flickable {
            id: licenseView
            anchors.fill: parent
            anchors.margins: Theme.spaceLg
            clip: true
            contentHeight: licenseText.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            RkText {
                id: licenseText
                objectName: "aboutLicenseText"
                width: licenseView.width
                text: App.licenseText
                role: "small"
                secondary: true
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
            }
        }
    }

    Flow {
        Layout.fillWidth: true
        visible: !dialog.showLicense
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
        RkButton { text: "Copy version details"; variant: "ghost"; onClicked: App.copy(App.details) },
        RkButton { text: "Project page"; onClicked: Repos.openUrl(App.homepage) },
        RkButton { id: closeButton; text: "Close"; variant: "primary"; hint: "Esc"; onClicked: dialog.close() }
    ]
}
