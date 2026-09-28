import QtQuick
import QtQuick.Layouts
import Repokase
import "../components"
import "fmt.js" as Fmt

// One repository in the list. Column geometry comes from `cols` (the list
// view) so header and rows always line up.
Item {
    id: row
    required property int index
    required property string nodeId
    required property string owner
    required property string name
    required property string description
    required property string visibility
    required property bool isArchived
    required property bool isFork
    required property bool isTemplate
    required property string language
    required property int stars
    required property int forks
    required property int watchers
    required property int issues
    required property int prs
    required property string pushedAt
    required property var topics
    required property var health
    required property bool marked

    property var cols
    property bool selected: false
    property bool keyboardFocus: false
    signal activated()
    signal picked(int modifiers)

    height: cols.rowHeight
    width: ListView.view ? ListView.view.width : 0

    Rectangle {
        anchors.fill: parent
        color: row.selected ? Theme.selectedFill : mouse.containsMouse ? Theme.hoverFill : "transparent"
    }
    // Selection marker, like the shell's selected menu rows.
    Rectangle {
        visible: row.selected
        width: 2
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        color: Theme.accent
    }
    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: Theme.borderWidth
        color: Theme.tint(Theme.fg, 0.05)
    }
    RkFocusFrame { shown: row.selected && row.keyboardFocus; anchors.margins: 0 }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: (m) => row.picked(m.modifiers)
        onDoubleClicked: row.activated()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: row.cols.padX
        anchors.rightMargin: row.cols.padX + row.cols.scrollInset
        spacing: row.cols.gap

        // Bulk-selection box: shown while anything is marked.
        Rectangle {
            visible: row.marked || row.cols.marking
            Layout.alignment: Qt.AlignVCenter
            width: Theme.fontBody; height: width
            radius: Theme.radius > 0 ? 2 : 0
            color: row.marked ? Theme.accent : "transparent"
            border.width: Theme.borderWidth
            border.color: row.marked ? Theme.accent : Theme.borderStrong
            RkText {
                anchors.centerIn: parent
                visible: row.marked
                text: "✓"
                role: "caption"
                color: Theme.accentFg
                font.weight: Font.Bold
            }
            MouseArea { anchors.fill: parent; onClicked: Repos.toggleMark(row.nodeId) }
            Accessible.role: Accessible.CheckBox
            Accessible.checked: row.marked
            Accessible.name: "Mark " + row.name
        }

        // ---------------------------------------------------- name + desc
        ColumnLayout {
            // Width comes only from leftover space, never from content, so
            // the fixed columns line up across rows.
            Layout.fillWidth: true
            Layout.preferredWidth: 0
            Layout.minimumWidth: 0
            Layout.alignment: Qt.AlignVCenter
            spacing: Theme.spaceXxs

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spaceMd
                RkText {
                    Layout.fillWidth: implicitWidth > width
                    Layout.maximumWidth: implicitWidth
                    text: row.owner + "/"
                    muted: true
                    visible: row.cols.showOwner(row.owner)
                }
                RkText {
                    Layout.maximumWidth: implicitWidth
                    Layout.fillWidth: implicitWidth > width
                    text: row.name
                    font.weight: Font.DemiBold
                    color: row.isArchived ? Theme.fgMuted : row.selected ? Theme.accent : Theme.fg
                }
                RkBadge { visible: row.visibility !== "PUBLIC"; text: row.visibility.toLowerCase(); tone: Theme.warning }
                RkBadge { visible: row.isArchived; text: "archived"; tone: Theme.fgMuted }
                RkBadge { visible: row.isFork; text: "fork"; tone: Theme.info }
                RkBadge { visible: row.isTemplate; text: "template"; tone: Theme.info }
                // Health: the worst issue, labelled (never color alone), +N for the rest.
                RkBadge {
                    readonly property var h: row.health || {}
                    readonly property var worst: h.flags && h.flags.length && h.level !== "info" ? h.flags[0] : null
                    visible: !!worst
                    text: worst ? worst.label + (h.flags.length > 1 ? " +" + (h.flags.length - 1) : "") : ""
                    tone: !worst ? Theme.fgMuted
                        : worst.severity === "critical" || worst.severity === "serious" ? Theme.danger
                        : Theme.warning
                    filled: !!worst && (worst.severity === "critical" || worst.severity === "serious")
                }
                Item { Layout.fillWidth: true }
            }
            RkText {
                Layout.fillWidth: true
                text: row.description.length ? row.description
                    : (row.topics && row.topics.length ? row.topics.join(" · ") : "No description")
                secondary: row.description.length > 0
                muted: row.description.length === 0
                role: "small"
            }
        }

        // ------------------------------------------------------- language
        RowLayout {
            Layout.preferredWidth: row.cols.langWidth
            Layout.minimumWidth: row.cols.langWidth
            Layout.maximumWidth: row.cols.langWidth
            visible: row.cols.showLang
            spacing: Theme.spaceMd
            Rectangle {
                visible: row.language.length > 0
                width: Theme.spaceMd + 2; height: width
                radius: Theme.radius > 0 ? width / 2 : 0
                color: Theme.seriesColor(row.language)
            }
            RkText { Layout.fillWidth: true; text: row.language; role: "small"; secondary: true }
        }

        // --------------------------------------------------------- counts
        Repeater {
            model: row.cols.numeric
            RkText {
                required property var modelData
                Layout.preferredWidth: row.cols.numWidth
                Layout.minimumWidth: row.cols.numWidth
                visible: modelData.visible
                horizontalAlignment: Text.AlignRight
                role: "small"
                readonly property int value: row[modelData.role]
                text: Fmt.count(value)
                color: value === 0 ? Theme.fgMuted
                    : (modelData.role === "issues" || modelData.role === "prs") ? Theme.fg
                    : Theme.fgSecondary
            }
        }

        RkText {
            Layout.preferredWidth: row.cols.dateWidth
            Layout.minimumWidth: row.cols.dateWidth
            horizontalAlignment: Text.AlignRight
            role: "small"
            muted: true
            text: Fmt.ago(row.pushedAt, Repos.now)
        }
    }
}
