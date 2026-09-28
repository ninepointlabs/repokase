import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Repokase
import "../components"
import "fmt.js" as Fmt

// Stats, links, categories, topics and recent workflow runs for the
// repository selected in the list.
Rectangle {
    id: root
    property var dialogs
    // Narrow windows show the pane full-width in place of the list.
    property bool showBack: false
    property var actions
    signal copied(string what)
    signal back()

    function focusFirst() { openButton.forceActiveFocus(Qt.TabFocusReason) }

    // Esc anywhere in the pane (not consumed by a field) goes back to the list.
    Keys.onEscapePressed: root.back()

    readonly property var repo: Detail.repo
    color: Theme.bgSunken

    function runTone(run) {
        const c = run.conclusion, s = run.status
        if (c === "success") return Theme.success
        if (c === "failure" || c === "timed_out" || c === "startup_failure") return Theme.danger
        if (c === "action_required") return Theme.warning
        if (c) return Theme.fgMuted // cancelled, skipped, neutral, stale
        return Theme.warning // queued / in_progress / waiting
    }
    function runLabel(run) {
        return run.conclusion ? run.conclusion.replace("_", " ") : (run.status || "").replace("_", " ")
    }
    function copy(text, what) { Repos.copy(text); copied(what) }

    Rectangle {
        anchors { top: parent.top; bottom: parent.bottom; left: parent.left }
        width: Theme.borderWidth
        color: Theme.border
    }

    Rectangle {
        id: backBar
        visible: root.showBack
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: visible ? Theme.controlHeight + 2 * Theme.spaceSm : 0
        color: Theme.bg
        RkButton {
            anchors.left: parent.left
            anchors.leftMargin: Theme.spaceLg
            anchors.verticalCenter: parent.verticalCenter
            variant: "ghost"
            text: "← Back to list"
            hint: "Esc"
            focusPolicy: Qt.TabFocus
            onClicked: root.back()
        }
        Rectangle {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: Theme.borderWidth
            color: Theme.border
        }
    }

    RkText {
        anchors.centerIn: parent
        visible: !Detail.hasRepo
        text: "Select a repository"
        muted: true
    }

    Flickable {
        id: flick
        anchors.fill: parent
        anchors.leftMargin: Theme.borderWidth
        anchors.topMargin: backBar.height
        visible: Detail.hasRepo
        contentHeight: body.implicitHeight + 2 * Theme.panelPadding
        // Vertical only: rows must fit the pane, never scroll sideways.
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        T.ScrollBar.vertical: RkScrollBar {}

        // Keep keyboard-focused controls in view while tabbing.
        function ensureVisible(item) {
            if (!item) return
            const p = item.mapToItem(body, 0, 0)
            if (p.y < contentY) contentY = Math.max(0, p.y - Theme.spaceLg)
            else if (p.y + item.height > contentY + height) contentY = Math.min(contentHeight - height, p.y + item.height - height + Theme.spaceLg)
        }
        Connections {
            target: root.Window.window
            function onActiveFocusItemChanged() {
                const f = root.Window.activeFocusItem
                let p = f
                while (p && p !== body) p = p.parent
                if (p === body) flick.ensureVisible(f)
            }
        }

        ColumnLayout {
            id: body
            objectName: "detailBody"
            x: Theme.panelPadding
            y: Theme.panelPadding
            width: flick.width - 2 * Theme.panelPadding
            spacing: Theme.spaceXxl

            // --------------------------------------------------- title
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.spaceSm
                RkText { Layout.fillWidth: true; text: (root.repo.owner || "") + " /"; muted: true; role: "small" }
                RkText {
                    Layout.fillWidth: true
                    text: root.repo.name || ""
                    role: "heading"
                    font.weight: Font.Bold
                    wrapMode: Text.WrapAnywhere
                    elide: Text.ElideNone
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.spaceSm
                    RkBadge { text: (root.repo.visibility || "").toLowerCase(); tone: root.repo.visibility === "PUBLIC" ? Theme.fgMuted : Theme.warning }
                    RkBadge { visible: !!root.repo.is_archived; text: "archived"; tone: Theme.fgMuted }
                    RkBadge { visible: !!root.repo.is_fork; text: "fork"; tone: Theme.info }
                    RkBadge { visible: !!root.repo.is_template; text: "template"; tone: Theme.info }
                    RkBadge { visible: !!root.repo.is_mirror; text: "mirror"; tone: Theme.info }
                }
                RkText {
                    Layout.fillWidth: true
                    text: root.repo.description || "No description"
                    secondary: !!root.repo.description
                    muted: !root.repo.description
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                }
            }

            RkButton {
                id: openButton
                Layout.fillWidth: true
                hint: "o"
                text: "Open on GitHub"
                variant: "primary"
                onClicked: Repos.openUrl(Detail.link("repo"))
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spaceMd
                RkButton { Layout.fillWidth: true; Layout.preferredWidth: 0; text: "Copy HTTPS"; onClicked: root.copy(Detail.cloneUrl("https"), "HTTPS clone URL") }
                RkButton { Layout.fillWidth: true; Layout.preferredWidth: 0; text: "Copy SSH"; onClicked: root.copy(Detail.cloneUrl("ssh"), "SSH clone URL") }
            }

            // --------------------------------------------------- health
            Section { title: "Health"; hint: "refreshes with the list" }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.spaceSm
                readonly property var h: root.repo.health || { level: "unknown", flags: [] }
                RkText {
                    Layout.fillWidth: true
                    visible: parent.h.flags.length === 0
                    text: parent.h.archived ? "Archived repositories aren't checked."
                        : parent.h.level === "unknown" ? "Not checked yet. Refresh to check."
                        : "✓ No issues found."
                    role: "small"
                    color: parent.h.level === "ok" && !parent.h.archived ? Theme.success : Theme.fgMuted
                }
                Repeater {
                    model: parent.h.flags
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Theme.spaceLg
                        RkBadge {
                            Layout.alignment: Qt.AlignTop
                            text: modelData.label
                            tone: modelData.severity === "critical" || modelData.severity === "serious" ? Theme.danger
                                : modelData.severity === "warning" ? Theme.warning : Theme.fgMuted
                            filled: modelData.severity === "critical" || modelData.severity === "serious"
                        }
                        RkText {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            text: modelData.detail
                            role: "small"
                            secondary: true
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                        }
                        RkButton {
                            visible: modelData.link.length > 0
                            variant: "ghost"
                            text: "View"
                            onClicked: Repos.openUrl(modelData.link)
                        }
                    }
                }
            }

            // -------------------------------------------------- manage
            Section { title: "Manage"; hint: "e · Shift+A · Shift+V · Del" }
            Flow {
                id: manage
                Layout.fillWidth: true
                spacing: Theme.spaceSm
                // Reading root.repo makes this re-evaluate after in-place changes
                // (archive, visibility) as well as on selection.
                readonly property var caps: Detail.hasRepo && root.repo.node_id ? Actions.capabilities(root.repo.node_id) : ({})

                RkButton {
                    text: "Edit description"
                    enabled: !!manage.caps.description && !Actions.busy
                    onClicked: root.actions.editDescription(Detail.nodeId)
                }
                RkButton {
                    text: root.repo.visibility === "PUBLIC" ? "Make private" : "Make public"
                    enabled: !!manage.caps.visibility && !Actions.busy
                    onClicked: root.actions.changeVisibility(Detail.nodeId)
                }
                RkButton {
                    text: root.repo.is_archived ? "Unarchive" : "Archive"
                    enabled: !!manage.caps.archive && !Actions.busy
                    onClicked: root.actions.toggleArchive(Detail.nodeId)
                }
                RkButton {
                    text: "Delete…"
                    variant: "danger"
                    enabled: !!manage.caps.delete && !Actions.busy
                    onClicked: root.actions.remove(Detail.nodeId)
                }
            }
            RkText {
                Layout.fillWidth: true
                readonly property var c: manage.caps
                visible: text.length > 0
                text: [c.descriptionWhy, c.visibilityWhy, c.deleteWhy].filter((x, i, a) => x && a.indexOf(x) === i).join(" ")
                role: "caption"
                muted: true
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
            }

            // --------------------------------------------------- stats
            Section { title: "Stats" }
            GridLayout {
                Layout.fillWidth: true
                columns: 4
                columnSpacing: Theme.spaceXl
                rowSpacing: Theme.spaceSm

                component Label: RkText { role: "small"; muted: true }
                component Value: RkText { Layout.fillWidth: true; Layout.preferredWidth: 0; Layout.minimumWidth: 0; role: "small" }

                Label { text: "Stars" }       Value { text: Fmt.count(root.repo.stargazers) }
                Label { text: "Forks" }       Value { text: Fmt.count(root.repo.forks) }
                Label { text: "Watchers" }    Value { text: Fmt.count(root.repo.watchers) }
                Label { text: "Language" }    Value { text: root.repo.primary_language || "—" }
                Label { text: "Open issues" } Value { text: String(root.repo.open_issues ?? 0); color: root.repo.open_issues > 0 ? Theme.fg : Theme.fgMuted }
                Label { text: "Open PRs" }    Value { text: String(root.repo.open_prs ?? 0); color: root.repo.open_prs > 0 ? Theme.fg : Theme.fgMuted }
                Label { text: "License" }     Value { text: root.repo.license_spdx && root.repo.license_spdx !== "NOASSERTION" ? root.repo.license_spdx : (root.repo.license_spdx ? "Other" : "None"); color: root.repo.license_spdx ? Theme.fg : Theme.warning }
                Label { text: "Branch" }      Value { text: root.repo.default_branch || "—" }
                Label { text: "Pushed" }      Value { text: Fmt.ago(root.repo.pushed_at, Repos.now) }
                Label { text: "Updated" }     Value { text: Fmt.ago(root.repo.updated_at, Repos.now) }
                Label { text: "Created" }     Value { text: root.repo.created_at ? root.repo.created_at.substring(0, 10) : "—" }
                Label { text: "Size" }        Value { text: root.repo.disk_kb >= 1024 ? (root.repo.disk_kb / 1024).toFixed(1) + " MB" : (root.repo.disk_kb || 0) + " KB" }
                Label { text: "Access" }      Value { text: (root.repo.viewer_permission || "—").toLowerCase() }
            }

            // --------------------------------------------------- links
            Section { title: "Open on GitHub" }
            Flow {
                Layout.fillWidth: true
                spacing: Theme.spaceSm
                Repeater {
                    model: [
                        { kind: "issues", text: "Issues" },
                        { kind: "pulls", text: "Pull requests" },
                        { kind: "actions", text: "Actions" },
                        { kind: "releases", text: "Releases" },
                        { kind: "insights", text: "Insights" },
                        { kind: "settings", text: "Settings", admin: true },
                    ]
                    RkButton {
                        required property var modelData
                        visible: !modelData.admin || Detail.canAdmin
                        text: modelData.text
                        variant: "secondary"
                        onClicked: Repos.openUrl(Detail.link(modelData.kind))
                    }
                }
            }

            // ----------------------------------------------- categories
            Section { title: "Categories"; hint: "local · 1–9 in list" }
            Flow {
                Layout.fillWidth: true
                spacing: Theme.spaceSm
                Repeater {
                    model: Repos.categories
                    RkChip {
                        required property var modelData
                        required property int index
                        text: (index < 9 ? (index + 1) + "  " : "") + modelData.name
                        showDot: true
                        tone: Theme.seriesAt(modelData.position)
                        checked: (root.repo.category_ids || []).indexOf(modelData.id) >= 0
                        onClicked: Repos.toggleCategory(Detail.nodeId, modelData.id)
                        Accessible.name: modelData.name + (checked ? ", assigned" : ", not assigned")
                    }
                }
                RkChip {
                    text: "+ New"
                    onClicked: root.dialogs.create()
                }
            }

            // --------------------------------------------------- topics
            Section { title: "Topics"; hint: "GitHub" }
            TopicEditor { Layout.fillWidth: true }

            // -------------------------------------------------- traffic
            Section { title: "Traffic"; hint: Traffic.lastSnapshot ? "recorded " + Fmt.ago(Traffic.lastSnapshot, Repos.now) : "" }
            ColumnLayout {
                id: trafficBox
                Layout.fillWidth: true
                spacing: Theme.spaceLg
                readonly property bool canPush: ["ADMIN", "MAINTAIN", "WRITE"].indexOf(root.repo.viewer_permission) >= 0
                // Reading lastSnapshot/running re-queries after each snapshot.
                readonly property var tdata: Detail.hasRepo && canPush && (Traffic.lastSnapshot !== null) && !Traffic.running
                    ? Traffic.forRepo(root.repo.full_name) : ({ views: [], clones: [], referrers: [], totals: {} })
                readonly property var totals: tdata.totals || {}
                property bool showTable: false

                RkText {
                    visible: !trafficBox.canPush
                    text: "GitHub only shares traffic with people who can push to the repository."
                    role: "small"
                    muted: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    Layout.fillWidth: true
                }

                // Headline numbers (last 14 days), then the long-term charts.
                RowLayout {
                    visible: trafficBox.canPush
                    Layout.fillWidth: true
                    spacing: Theme.spaceXl
                    Repeater {
                        model: [
                            { label: "Views · 14 days", value: trafficBox.totals.views14, sub: (trafficBox.totals.viewUniques14 || 0) + " unique" },
                            { label: "Clones · 14 days", value: trafficBox.totals.clones14, sub: (trafficBox.totals.cloneUniques14 || 0) + " unique" },
                            { label: "History", value: trafficBox.totals.days || 0, sub: trafficBox.totals.since ? "since " + trafficBox.totals.since.substring(5).replace("-", "/") : "not recorded yet", suffix: " days" },
                        ]
                        ColumnLayout {
                            required property var modelData
                            // Share the row equally; never widen the pane.
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            Layout.minimumWidth: 0
                            spacing: 0
                            RkText { Layout.fillWidth: true; text: modelData.label; role: "caption"; muted: true }
                            RkText { Layout.fillWidth: true; text: Fmt.count(modelData.value || 0) + (modelData.suffix || ""); role: "heading"; font.weight: Font.DemiBold }
                            RkText { Layout.fillWidth: true; text: modelData.sub; role: "caption"; secondary: true }
                        }
                    }
                }

                RkLineChart {
                    visible: trafficBox.canPush
                    Layout.fillWidth: true
                    title: "Views"
                    unit: "views"
                    color: Theme.accent
                    points: trafficBox.tdata.views || []
                }
                RkLineChart {
                    visible: trafficBox.canPush
                    Layout.fillWidth: true
                    title: "Clones"
                    unit: "clones"
                    color: Theme.info
                    points: trafficBox.tdata.clones || []
                }

                RowLayout {
                    visible: trafficBox.canPush
                    Layout.fillWidth: true
                    spacing: Theme.spaceSm
                    RkChip {
                        text: trafficBox.showTable ? "Hide table" : "Show table"
                        checked: trafficBox.showTable
                        onClicked: trafficBox.showTable = !trafficBox.showTable
                    }
                    Item { Layout.fillWidth: true }
                    RkText { visible: Traffic.running; text: Traffic.progress; role: "caption"; muted: true }
                    RkButton {
                        variant: "ghost"
                        text: "Record now"
                        enabled: !Traffic.running
                        onClicked: Traffic.snapshotNow()
                    }
                }
                RkNotice { Layout.fillWidth: true; kind: "danger"; text: Traffic.error }

                // Table view: the same numbers, newest first.
                GridLayout {
                    visible: trafficBox.canPush && trafficBox.showTable
                    Layout.fillWidth: true
                    columns: 5
                    columnSpacing: Theme.spaceXl
                    rowSpacing: Theme.spaceXxs
                    Repeater {
                        model: ["Day", "Views", "Unique", "Clones", "Unique"]
                        RkText { required property string modelData; text: modelData; role: "caption"; muted: true; Layout.fillWidth: modelData === "Day" }
                    }
                    Repeater {
                        model: {
                            const v = trafficBox.tdata.views || [], c = trafficBox.tdata.clones || []
                            const rows = []
                            for (let i = v.length - 1; i >= 0 && rows.length < 30; i--)
                                rows.push([v[i].day, v[i].count, v[i].uniques, c[i] ? c[i].count : 0, c[i] ? c[i].uniques : 0])
                            return [].concat(...rows)
                        }
                        RkText {
                            required property var modelData
                            required property int index
                            text: modelData
                            role: "small"
                            color: index % 5 === 0 ? Theme.fgSecondary : (modelData === 0 ? Theme.fgMuted : Theme.fg)
                            horizontalAlignment: index % 5 === 0 ? Text.AlignLeft : Text.AlignRight
                            Layout.fillWidth: index % 5 === 0
                        }
                    }
                }

                ColumnLayout {
                    visible: trafficBox.canPush && (trafficBox.tdata.referrers || []).length > 0
                    Layout.fillWidth: true
                    spacing: Theme.spaceXxs
                    RkText { text: "Top referrers · 14 days"; role: "caption"; muted: true }
                    Repeater {
                        model: (trafficBox.tdata.referrers || []).slice(0, 5)
                        RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            RkText { Layout.fillWidth: true; text: modelData.referrer; role: "small" }
                            RkText { text: modelData.count + " · " + modelData.uniques + " unique"; role: "small"; secondary: true }
                        }
                    }
                }
            }

            // ----------------------------------------------------- runs
            Section { title: "Workflow runs"; hint: Detail.runsSynced ? "synced " + Fmt.ago(Detail.runsSynced, Repos.now) : "" }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spaceMd
                RkButton {
                    visible: Workflows.canRun(Detail.nodeId)
                    text: "Run workflow…"
                    onClicked: workflowDialog.start(Detail.nodeId)
                }
                Item { Layout.fillWidth: true }
                RkButton {
                    variant: "ghost"
                    text: Detail.runsLoading ? "…" : "Refresh"
                    enabled: !Detail.runsLoading
                    onClicked: Detail.refreshRuns()
                }
            }
            RkBusyBar { Layout.fillWidth: true; running: Detail.runsLoading }
            RkNotice { Layout.fillWidth: true; kind: "danger"; text: Detail.runsError }
            RowLayout {
                Layout.fillWidth: true
                visible: Workflows.error.length > 0 && !workflowDialog.visible
                RkNotice { Layout.fillWidth: true; kind: "danger"; text: Workflows.error }
                RkButton { visible: Workflows.errorUrl.length > 0; text: "Authorize SSO"; onClicked: Repos.openUrl(Workflows.errorUrl) }
                RkButton { text: "Dismiss"; variant: "ghost"; onClicked: Workflows.clearError() }
            }
            RkText {
                visible: !Detail.runsLoading && Detail.runs.length === 0 && !Detail.runsError
                text: Detail.runsSynced ? "No workflow runs" : "Loading…"
                muted: true
                role: "small"
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Repeater {
                    model: Detail.runs
                    T.AbstractButton {
                        id: runRow
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: runCol.implicitHeight + 2 * Theme.spaceMd
                        focusPolicy: Qt.StrongFocus
                        hoverEnabled: true
                        onClicked: Repos.openUrl(modelData.html_url)
                        Keys.onReturnPressed: clicked()
                        Accessible.name: modelData.name + " " + root.runLabel(modelData)

                        background: Rectangle {
                            color: runRow.hovered ? Theme.hoverFill : "transparent"
                            radius: Theme.radius
                            RkFocusFrame { shown: runRow.activeFocus && runRow.focusReason !== Qt.MouseFocusReason; anchors.margins: 0 }
                        }
                        contentItem: RowLayout {
                            id: runCol
                            spacing: Theme.spaceLg
                            RkBadge {
                                Layout.preferredWidth: 11 * Theme.fontCaption * 0.62 + 2 * Theme.spaceMd
                                text: root.runLabel(runRow.modelData)
                                tone: root.runTone(runRow.modelData)
                                filled: true
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                RkText {
                                    Layout.fillWidth: true
                                    text: runRow.modelData.name + (runRow.modelData.run_number ? "  #" + runRow.modelData.run_number : "")
                                    role: "small"
                                }
                                RkText {
                                    Layout.fillWidth: true
                                    text: [runRow.modelData.head_branch, runRow.modelData.event, Fmt.ago(runRow.modelData.created_at, Repos.now)].filter((x) => !!x).join(" · ")
                                    role: "caption"
                                    muted: true
                                }
                            }
                            // Run controls (write access). Failed runs offer both re-runs.
                            Row {
                                visible: Workflows.canRun(Detail.nodeId)
                                spacing: Theme.spaceXs
                                readonly property var r: runRow.modelData
                                readonly property bool active: !r.conclusion
                                readonly property bool failed: ["failure", "timed_out", "cancelled", "startup_failure"].indexOf(r.conclusion) >= 0
                                RkButton {
                                    visible: parent.failed && parent.r.conclusion !== "cancelled"
                                    variant: "ghost"; text: "Re-run failed"
                                    enabled: !Workflows.busy
                                    onClicked: Workflows.runAction(Detail.nodeId, parent.r.id, "rerun-failed")
                                }
                                RkButton {
                                    visible: !parent.active
                                    variant: "ghost"; text: "Re-run"
                                    enabled: !Workflows.busy
                                    onClicked: Workflows.runAction(Detail.nodeId, parent.r.id, "rerun")
                                }
                                RkButton {
                                    visible: parent.active
                                    variant: "ghost"; text: "Cancel"
                                    enabled: !Workflows.busy
                                    onClicked: Workflows.runAction(Detail.nodeId, parent.r.id, "cancel")
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    WorkflowDialog { id: workflowDialog }

    component Section: RowLayout {
        property string title: ""
        property string hint: ""
        Layout.fillWidth: true
        spacing: Theme.spaceMd
        RkText { text: parent.title.toUpperCase(); role: "caption"; muted: true; font.letterSpacing: 1 }
        Rectangle { Layout.fillWidth: true; Layout.minimumWidth: Theme.spaceXl; height: Theme.borderWidth; color: Theme.border }
        RkText {
            visible: parent.hint.length > 0
            Layout.maximumWidth: 20 * Theme.fontCaption * 0.62  // fixed cap: a width-relative one recurses
            text: parent.hint
            role: "caption"
            muted: true
        }
    }
}
