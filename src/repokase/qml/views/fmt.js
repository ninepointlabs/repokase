.pragma library

// Compact counts: 999, 1.2k, 12k, 1.3M
function count(n) {
    if (n === undefined || n === null) return ""
    if (n < 1000) return String(n)
    if (n < 10000) return (Math.round(n / 100) / 10) + "k"
    if (n < 1000000) return Math.round(n / 1000) + "k"
    return (Math.round(n / 100000) / 10) + "M"
}

// "just now", "5m", "3h", "2d", "4mo", "2y" relative to nowMs.
function ago(iso, nowMs) {
    if (!iso) return "never"
    const t = Date.parse(iso)
    if (isNaN(t)) return ""
    const s = Math.max(0, (nowMs - t) / 1000)
    if (s < 60) return "just now"
    if (s < 3600) return Math.floor(s / 60) + "m ago"
    if (s < 86400) return Math.floor(s / 3600) + "h ago"
    if (s < 86400 * 30) return Math.floor(s / 86400) + "d ago"
    if (s < 86400 * 365) return Math.floor(s / (86400 * 30)) + "mo ago"
    return Math.floor(s / (86400 * 365)) + "y ago"
}

function agoMs(ms, nowMs) {
    return ms > 0 ? ago(new Date(ms).toISOString(), nowMs) : "never"
}

function clock(ms) {
    if (!ms) return ""
    const d = new Date(ms)
    const pad = (x) => (x < 10 ? "0" : "") + x
    return pad(d.getHours()) + ":" + pad(d.getMinutes())
}
