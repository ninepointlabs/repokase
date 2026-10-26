import QtQuick
import QtQuick.Window
import Repokase
import "views"

Window {
    id: window
    title: App.name
    width: 1180
    height: 760
    minimumWidth: 640
    minimumHeight: 420
    visible: true
    color: Theme.bg

    Shortcut {
        sequences: [StandardKey.Quit]
        onActivated: Qt.quit()
    }
    Shortcut {
        sequences: ["F1", "?"]
        onActivated: about.visible ? about.close() : about.open()
    }

    Loader {
        id: page
        anchors.fill: parent
        focus: true
        sourceComponent: App.cacheError.length ? cacheError : Auth.state === "signedIn" ? home : login
    }

    Component { id: cacheError; CacheErrorView {} }
    Component { id: login; LoginView {} }
    Component { id: home; HomeView { onAboutRequested: about.open() } }

    AboutDialog { id: about }
}
