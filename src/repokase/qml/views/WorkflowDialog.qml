import QtQuick
import QtQuick.Layouts
import Repokase
import "../components"

// Run a workflow_dispatch workflow: pick workflow + branch, fill its inputs.
RkDialog {
    id: dialog
    property string nodeId: ""
    property int workflowIndex: 0
    property string ref: ""
    property var values: ({})

    readonly property var workflows: Workflows.dispatchables
    readonly property var wf: workflows.length > workflowIndex ? workflows[workflowIndex] : null
    readonly property bool ready: !Workflows.loading && Workflows.loadedFor === nodeId

    function start(id) {
        nodeId = id
        workflowIndex = 0
        values = ({})
        Workflows.clearError()
        Workflows.loadDispatch(id)
        show(null, null)
    }
    function setValue(name, v) { const next = Object.assign({}, values); next[name] = v; values = next }
    function valueOf(inp) { return values[inp.name] !== undefined ? values[inp.name] : inp.default }
    function run() {
        if (!wf) return
        Workflows.dispatch(nodeId, wf.id, ref || Workflows.defaultBranch, values)
    }

    title: "Run workflow · " + (Repos.repo(nodeId).full_name || "")
    width: Math.min(parent ? parent.width - 2 * Theme.spaceHuge : 560, 44 * Theme.fontBody)
    onWfChanged: values = ({})
    Connections {
        target: Workflows
        function onDone() { if (dialog.visible) dialog.close() }
    }

    RkBusyBar { Layout.fillWidth: true; running: Workflows.loading }
    RkText {
        Layout.fillWidth: true
        visible: dialog.ready && dialog.workflows.length === 0 && !Workflows.error
        text: "No workflows in this repository can be run manually. Add a workflow_dispatch trigger to a workflow to run it from here."
        muted: true
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
    }

    GridLayout {
        visible: dialog.ready && dialog.workflows.length > 0
        Layout.fillWidth: true
        columns: 2
        columnSpacing: Theme.spaceXl
        rowSpacing: Theme.spaceMd

        RkText { text: "Workflow"; muted: true }
        RkComboBox {
            id: wfBox
            Layout.fillWidth: true
            accentNonDefault: false
            model: dialog.workflows.map((w, i) => ({ text: w.name, value: i }))
            current: dialog.workflowIndex
            onPicked: (v) => dialog.workflowIndex = v
        }
        RkText { text: "Branch"; muted: true }
        RkComboBox {
            Layout.fillWidth: true
            accentNonDefault: false
            model: Workflows.branches.map((b) => ({ text: b, value: b }))
            current: dialog.ref || Workflows.defaultBranch
            onPicked: (v) => dialog.ref = v
        }

    }

    ColumnLayout {
        visible: dialog.ready && !!dialog.wf && dialog.wf.inputs.length > 0
        Layout.fillWidth: true
        spacing: Theme.spaceLg
        Repeater {
            model: dialog.wf ? dialog.wf.inputs : []
            ColumnLayout {
                id: field
                required property var modelData
                Layout.fillWidth: true
                spacing: Theme.spaceXs
                RkText {
                    text: field.modelData.name + (field.modelData.required ? " *" : "")
                    font.weight: Font.DemiBold
                    role: "small"
                }
                RkText {
                    Layout.fillWidth: true
                    visible: field.modelData.description.length > 0
                    text: field.modelData.description
                    role: "caption"
                    muted: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                }
                RkTextField {
                    Layout.fillWidth: true
                    visible: ["string", "number", "environment"].indexOf(field.modelData.type) >= 0
                    text: dialog.valueOf(field.modelData)
                    placeholderText: field.modelData.type === "number" ? "number" : field.modelData.type === "environment" ? "environment name" : ""
                    onTextEdited: dialog.setValue(field.modelData.name, text)
                    onAccepted: dialog.run()
                }
                RkComboBox {
                    Layout.fillWidth: true
                    visible: field.modelData.type === "choice"
                    accentNonDefault: false
                    model: field.modelData.options.map((o) => ({ text: o, value: o }))
                    current: dialog.valueOf(field.modelData)
                    onPicked: (v) => dialog.setValue(field.modelData.name, v)
                }
                RkChip {
                    visible: field.modelData.type === "boolean"
                    readonly property bool on: String(dialog.valueOf(field.modelData)) === "true"
                    text: on ? "✓ true" : "false"
                    checked: on
                    tone: Theme.accent
                    onClicked: dialog.setValue(field.modelData.name, on ? "false" : "true")
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        visible: Workflows.error.length > 0
        RkNotice { Layout.fillWidth: true; kind: "danger"; text: Workflows.error }
        RkButton { visible: Workflows.errorUrl.length > 0; text: "Authorize SSO"; onClicked: Repos.openUrl(Workflows.errorUrl) }
    }

    buttons: [
        RkButton { text: "Cancel"; variant: "ghost"; hint: "Esc"; onClicked: dialog.close() },
        RkButton {
            text: Workflows.busy ? "Starting…" : "Run workflow"
            variant: "primary"
            enabled: dialog.ready && !!dialog.wf && !Workflows.busy
            onClicked: dialog.run()
        }
    ]
}
