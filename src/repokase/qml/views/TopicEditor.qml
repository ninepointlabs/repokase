import QtQuick
import QtQuick.Layouts
import Repokase
import "../components"

// GitHub topics for the selected repo. Edits stay local until Save, which
// replaces the full topic list on GitHub (PUT /repos/{repo}/topics).
ColumnLayout {
    id: root
    spacing: Theme.spaceMd

    readonly property var saved: Detail.repo.topics || []
    property var draft: []
    property string inputError: ""
    readonly property bool dirty: JSON.stringify(draft) !== _savedKey
    readonly property bool editable: Detail.canAdmin

    function reset() { draft = saved.slice(); inputError = ""; field.clear(); Detail.clearTopicsError() }
    // `repo` is re-read as a fresh map on every change; only reset when the
    // saved topic list itself differs.
    property string _savedKey: "[]"
    onSavedChanged: {
        const k = JSON.stringify(saved)
        if (k !== _savedKey) { _savedKey = k; reset() }
    }

    function add(raw) {
        const parts = raw.split(/[,\s]+/).filter((p) => p.length)
        const next = draft.slice()
        for (const p of parts) {
            const r = Detail.checkTopic(p)
            if (!r.ok) { inputError = r.error; return false }
            if (next.indexOf(r.topic) < 0) next.push(r.topic)
        }
        if (next.length > 20) { inputError = "GitHub allows at most 20 topics per repository."; return false }
        draft = next
        inputError = ""
        return true
    }
    function removeAt(i) {
        const next = draft.slice(); next.splice(i, 1); draft = next
        field.forceActiveFocus(Qt.TabFocusReason)
    }

    Flow {
        Layout.fillWidth: true
        spacing: Theme.spaceSm
        Repeater {
            model: root.draft
            RkChip {
                required property string modelData
                required property int index
                text: modelData
                tone: Theme.info
                removable: root.editable && !Detail.topicsBusy
                focusPolicy: root.editable ? Qt.StrongFocus : Qt.NoFocus
                onRemoved: root.removeAt(index)
            }
        }
        RkText {
            visible: root.draft.length === 0
            text: "No topics"
            muted: true
            role: "small"
        }
    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.editable
        spacing: Theme.spaceMd
        RkTextField {
            id: field
            objectName: "topicField"
            Layout.fillWidth: true
            implicitWidth: 10 * Theme.fontBody
            placeholderText: "Add topic, Enter"
            enabled: !Detail.topicsBusy
            onTextEdited: root.inputError = ""
            onAccepted: if (text.trim().length && root.add(text)) clear()
            Keys.onPressed: (e) => {
                if (e.key === Qt.Key_Backspace && text.length === 0 && root.draft.length) {
                    root.removeAt(root.draft.length - 1); e.accepted = true
                } else if (e.key === Qt.Key_S && (e.modifiers & Qt.ControlModifier) && root.dirty) {
                    Detail.saveTopics(root.draft); e.accepted = true
                } else if (e.key === Qt.Key_Escape && root.dirty) {
                    root.reset(); e.accepted = true
                }
            }
        }
        RkButton {
            text: Detail.topicsBusy ? "Saving…" : "Save"
            variant: "primary"
            hint: "Ctrl+S"
            enabled: root.dirty && !Detail.topicsBusy
            onClicked: Detail.saveTopics(root.draft)
        }
        RkButton {
            visible: root.dirty && !Detail.topicsBusy
            text: "Revert"
            variant: "ghost"
            onClicked: root.reset()
        }
    }

    RkNotice { Layout.fillWidth: true; kind: "warning"; text: root.inputError }
    RkNotice { Layout.fillWidth: true; kind: "danger"; text: Detail.topicsError }
    RkText {
        Layout.fillWidth: true
        visible: !root.editable && Detail.hasRepo
        text: "Editing topics needs admin or maintain access."
        role: "caption"
        muted: true
    }
}
