import QtQuick
import QtQuick.Layouts
import Repokase
import "../components"

// Device-flow sign in. Keys: Enter = primary action, C = copy code,
// O = open browser, Esc = cancel.
FocusScope {
    id: root
    focus: true

    readonly property bool waiting: Auth.state === "awaitingUser"
    readonly property bool requesting: Auth.state === "requesting" || Auth.state === "starting"
    property int secondsLeft: 0

    Timer {
        interval: 1000
        repeat: true
        triggeredOnStart: true
        running: root.waiting
        onTriggered: root.secondsLeft = Math.max(0, Math.round((Auth.expiresAt - Date.now()) / 1000))
    }

    function fmt(s) {
        const m = Math.floor(s / 60)
        const r = s % 60
        return m + ":" + (r < 10 ? "0" : "") + r
    }

    Keys.onPressed: (event) => {
        if (!root.waiting) return
        if (event.key === Qt.Key_C && !(event.modifiers & Qt.ControlModifier)) {
            Auth.copyCode(); copied.restart(); event.accepted = true
        } else if (event.key === Qt.Key_O) {
            Auth.openBrowser(); event.accepted = true
        } else if (event.key === Qt.Key_Escape) {
            Auth.cancelLogin(); event.accepted = true
        }
    }

    onWaitingChanged: if (waiting) openButton.forceActiveFocus(Qt.TabFocusReason); else signInButton.forceActiveFocus(Qt.TabFocusReason)
    Component.onCompleted: signInButton.forceActiveFocus(Qt.TabFocusReason)

    Timer { id: copied; interval: 1600 }

    RkPane {
        id: card
        level: "sunken"
        anchors.centerIn: parent
        width: Math.min(parent.width - 2 * Theme.spaceHuge, 30 * Theme.fontBody + 2 * Theme.panelPadding)
        height: body.implicitHeight + 2 * Theme.panelPadding
        padding: Theme.panelPadding

        ColumnLayout {
            id: body
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: Theme.spaceXxl

            ColumnLayout {
                spacing: Theme.spaceXs
                RkText { text: App.name; role: "display"; font.weight: Font.Bold; color: Theme.accent }
                RkText { text: App.tagline; secondary: true }
            }

            Rectangle { Layout.fillWidth: true; height: Theme.borderWidth; color: Theme.border }

            // ---------------------------------------------- idle / error
            ColumnLayout {
                visible: !root.waiting
                Layout.fillWidth: true
                spacing: Theme.spaceXl

                RkText {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    secondary: true
                    text: Auth.reason.length ? Auth.reason
                        : "Sign in with GitHub to see and manage your repositories. " +
                          "You'll approve access in your browser; Repokase never sees your password."
                }
                RkNotice { Layout.fillWidth: true; kind: "danger"; text: Auth.error }
                RkNotice { Layout.fillWidth: true; kind: "warning"; text: Auth.notice }
                RkButton {
                    id: signInButton
                    Layout.fillWidth: true
                    variant: "primary"
                    enabled: !root.requesting
                    text: root.requesting ? (Auth.state === "starting" ? "Checking keyring…" : "Contacting GitHub…")
                        : Auth.error.length ? "Try again" : "Sign in with GitHub"
                    hint: "Enter"
                    onClicked: Auth.startLogin()
                }
                RkBusyBar { Layout.fillWidth: true; running: root.requesting }
            }

            // ---------------------------------------------- awaiting user
            ColumnLayout {
                visible: root.waiting
                Layout.fillWidth: true
                spacing: Theme.spaceXl

                RkText {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    secondary: true
                    text: "Open " + Auth.verificationUri.replace("https://", "") + " and enter this code:"
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: code.implicitHeight + 2 * Theme.spaceXl
                    color: Theme.bgInset
                    radius: Theme.radius
                    border.width: Theme.borderWidth
                    border.color: Theme.border
                    RkText {
                        id: code
                        anchors.centerIn: parent
                        text: Auth.userCode
                        role: "display"
                        font.weight: Font.Bold
                        font.letterSpacing: Theme.spaceSm
                        color: Theme.fg
                    }
                    Accessible.role: Accessible.StaticText
                    Accessible.name: "Device code " + Auth.userCode
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spaceLg
                    RkButton {
                        id: openButton
                        Layout.fillWidth: true
                        variant: "primary"
                        text: "Open browser"
                        hint: "O"
                        onClicked: Auth.openBrowser()
                        KeyNavigation.right: copyButton
                    }
                    RkButton {
                        id: copyButton
                        Layout.fillWidth: true
                        text: copied.running ? "Copied" : "Copy code"
                        hint: "C"
                        onClicked: { Auth.copyCode(); copied.restart() }
                        KeyNavigation.left: openButton
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    RkBusyBar { Layout.fillWidth: true; running: root.waiting }
                    RkText {
                        muted: true
                        role: "small"
                        text: "Waiting… " + root.fmt(root.secondsLeft)
                    }
                }

                RkButton {
                    Layout.alignment: Qt.AlignRight
                    variant: "ghost"
                    text: "Cancel"
                    hint: "Esc"
                    onClicked: Auth.cancelLogin()
                }
            }
        }
    }
}
