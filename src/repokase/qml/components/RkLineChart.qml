import QtQuick
import Repokase

// Single-series daily line chart (one y-scale; the title names the series,
// so there is no legend). Hover or focus + ←/→ moves a crosshair whose
// tooltip shows the day's count and unique visitors.
Item {
    id: chart

    property var points: []            // [{ day: "YYYY-MM-DD", count, uniques }]
    property string title: ""
    property string unit: "views"
    property color color: Theme.accent
    property int hover: -1

    readonly property int n: points ? points.length : 0
    readonly property int maxValue: {
        let m = 0
        for (let i = 0; i < n; i++) m = Math.max(m, points[i].count)
        return m
    }
    // A "nice" ceiling for the axis: 1, 2, 5 × 10^k.
    readonly property int axisMax: {
        if (maxValue <= 4) return 4
        const p = Math.pow(10, Math.floor(Math.log10(maxValue)))
        for (const f of [1, 2, 5, 10]) if (f * p >= maxValue) return f * p
        return maxValue
    }
    readonly property real gutterLeft: Theme.fontCaption * 0.62 * Math.max(2, String(axisMax).length) + Theme.spaceMd
    readonly property real gutterBottom: Theme.fontCaption + Theme.spaceMd
    readonly property real plotTop: titleRow.height + Theme.spaceMd
    readonly property real plotW: Math.max(1, width - gutterLeft - Theme.spaceSm)
    readonly property real plotH: Math.max(1, height - plotTop - gutterBottom)

    function xAt(i) { return gutterLeft + (n <= 1 ? plotW / 2 : i * plotW / (n - 1)) }
    function yAt(v) { return plotTop + plotH - (v / axisMax) * plotH }
    function fmtDay(iso, withYear) {
        if (!iso) return ""
        const d = new Date(iso + "T00:00:00Z")
        const m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()]
        return m + " " + d.getUTCDate() + (withYear ? ", " + d.getUTCFullYear() : "")
    }
    function total() { let t = 0; for (let i = 0; i < n; i++) t += points[i].count; return t }

    implicitHeight: Theme.controlHeight * 4.5
    activeFocusOnTab: true
    Accessible.role: Accessible.Chart
    Accessible.name: title + ": " + total() + " " + unit + " over " + n + " days"

    onPointsChanged: { hover = -1; canvas.requestPaint() }
    onHoverChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
    Connections { target: Theme; function onChanged() { canvas.requestPaint() } }

    Keys.onLeftPressed: hover = hover < 0 ? n - 1 : Math.max(0, hover - 1)
    Keys.onRightPressed: hover = hover < 0 ? n - 1 : Math.min(n - 1, hover + 1)
    Keys.onPressed: (e) => {
        if (e.key === Qt.Key_Home) { hover = 0; e.accepted = true }
        else if (e.key === Qt.Key_End) { hover = n - 1; e.accepted = true }
    }
    onActiveFocusChanged: if (!activeFocus) hover = -1

    Row {
        id: titleRow
        spacing: Theme.spaceMd
        RkText { text: chart.title; role: "small"; font.weight: Font.DemiBold }
        RkText { text: chart.total() + " total"; role: "caption"; muted: true; anchors.baseline: parent.children[0].baseline }
    }

    // y labels: 0, half, max (recessive)
    Repeater {
        model: [0, chart.axisMax / 2, chart.axisMax]
        RkText {
            required property var modelData
            x: 0
            width: chart.gutterLeft - Theme.spaceMd
            horizontalAlignment: Text.AlignRight
            y: chart.yAt(modelData) - height / 2
            text: Number.isInteger(modelData) ? modelData : modelData.toFixed(1)
            role: "caption"
            muted: true
        }
    }
    // x labels: first and last day
    RkText {
        visible: chart.n > 0
        x: chart.gutterLeft
        y: chart.plotTop + chart.plotH + Theme.spaceSm
        text: chart.n ? chart.fmtDay(chart.points[0].day, true) : ""
        role: "caption"
        muted: true
    }
    RkText {
        visible: chart.n > 1
        x: chart.gutterLeft + chart.plotW - width
        y: chart.plotTop + chart.plotH + Theme.spaceSm
        text: chart.n ? chart.fmtDay(chart.points[chart.n - 1].day) : ""
        role: "caption"
        muted: true
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: true
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const c = chart
            // Grid: recessive hairlines at 0, half, max.
            ctx.lineWidth = 1
            ctx.strokeStyle = Theme.border
            for (const v of [0, c.axisMax / 2, c.axisMax]) {
                const y = Math.round(c.yAt(v)) + 0.5
                ctx.beginPath(); ctx.moveTo(c.gutterLeft, y); ctx.lineTo(c.gutterLeft + c.plotW, y); ctx.stroke()
            }
            if (c.n === 0) return
            // Area (quiet) then the 2px line.
            ctx.beginPath()
            ctx.moveTo(c.xAt(0), c.yAt(0))
            for (let i = 0; i < c.n; i++) ctx.lineTo(c.xAt(i), c.yAt(c.points[i].count))
            ctx.lineTo(c.xAt(c.n - 1), c.yAt(0))
            ctx.closePath()
            ctx.fillStyle = Theme.tint(c.color, 0.14)
            ctx.fill()
            ctx.beginPath()
            for (let i = 0; i < c.n; i++) {
                const x = c.xAt(i), y = c.yAt(c.points[i].count)
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
            }
            ctx.lineWidth = 2
            ctx.lineJoin = "round"
            ctx.strokeStyle = c.color
            ctx.stroke()
            // Crosshair + marker with a surface ring.
            if (c.hover >= 0 && c.hover < c.n) {
                const x = Math.round(c.xAt(c.hover)) + 0.5
                ctx.lineWidth = 1
                ctx.strokeStyle = Theme.fgMuted
                ctx.beginPath(); ctx.moveTo(x, c.plotTop); ctx.lineTo(x, c.plotTop + c.plotH); ctx.stroke()
                const y = c.yAt(c.points[c.hover].count)
                ctx.beginPath(); ctx.arc(x, y, 5, 0, 2 * Math.PI)
                ctx.fillStyle = c.color; ctx.fill()
                ctx.lineWidth = 2; ctx.strokeStyle = Theme.bgSunken; ctx.stroke()
            }
        }
    }

    RkText {
        anchors.centerIn: parent
        visible: chart.n === 0
        text: "No data recorded yet"
        muted: true
        role: "small"
    }

    MouseArea {
        x: chart.gutterLeft
        y: chart.plotTop
        width: chart.plotW
        height: chart.plotH
        hoverEnabled: true
        onPositionChanged: (m) => {
            if (chart.n === 0) return
            chart.hover = chart.n === 1 ? 0 : Math.max(0, Math.min(chart.n - 1, Math.round(m.x / (chart.plotW / (chart.n - 1)))))
        }
        onExited: if (!chart.activeFocus) chart.hover = -1
    }

    // Tooltip: text in text tokens; the colored dot carries identity.
    Rectangle {
        id: tip
        visible: chart.hover >= 0 && chart.hover < chart.n
        readonly property var p: visible ? chart.points[chart.hover] : null
        width: tipCol.implicitWidth + 2 * Theme.spaceLg
        height: tipCol.implicitHeight + 2 * Theme.spaceMd
        // Beside the crosshair inside the plot, flipping sides near the right edge.
        readonly property real cx: chart.xAt(Math.max(0, chart.hover))
        x: cx + Theme.spaceLg + width <= chart.width ? cx + Theme.spaceLg : Math.max(chart.gutterLeft, cx - Theme.spaceLg - width)
        y: chart.plotTop + Theme.spaceXs
        z: 5
        color: Theme.bgRaised
        radius: Theme.radius
        border.width: Theme.borderWidth
        border.color: Theme.borderStrong
        Column {
            id: tipCol
            anchors.centerIn: parent
            spacing: Theme.spaceXxs
            RkText { text: tip.p ? chart.fmtDay(tip.p.day, true) : ""; role: "caption"; muted: true }
            Row {
                spacing: Theme.spaceSm
                Rectangle { width: Theme.spaceMd; height: width; radius: width / 2; color: chart.color; anchors.verticalCenter: parent.verticalCenter }
                RkText { text: tip.p ? tip.p.count + " " + chart.unit : ""; role: "small"; font.weight: Font.DemiBold }
            }
            RkText { text: tip.p ? tip.p.uniques + " unique" : ""; role: "caption"; secondary: true }
        }
    }

    RkFocusFrame { shown: chart.activeFocus && chart.focusReason !== Qt.MouseFocusReason; anchors.margins: -2 }
}
