import QtQuick
import Quickshell
import "qml" as Plugin

// Standalone Quickshell config used only by tests/test_qml_process_probe.py.
// It sits at repository root so its import of the production qml/ directory
// remains inside Quickshell's config-root import boundary.
ShellRoot {
    id: root

    property bool finished: false
    property int completedLists: 0

    function finish(success, reason) {
        if (finished) return
        finished = true
        console.log("LAYOUTCTL_PROCESS_PROBE=" + JSON.stringify({ success: success, reason: reason }))
        Qt.quit()
    }

    Plugin.LayoutctlClient {
        id: layoutctl
        onProfileListFinished: function(exitCode, response, stderrText) {
            const valid = exitCode === 0
                && response !== null
                && response.contractVersion === 1
                && response.status === "ok"
                && response.data !== null
                && Array.isArray(response.data.profiles)
                && stderrText === ""
            if (!valid) {
                root.finish(false, "unexpected process result")
                return
            }
            root.completedLists += 1
            if (root.completedLists === 1) {
                if (!layoutctl.listProfiles()) root.finish(false, "callback could not enqueue the next command")
                return
            }
            root.finish(true, "ok")
        }
    }

    Component.onCompleted: {
        if (!layoutctl.listProfiles()) finish(false, "process did not start")
    }

    Timer {
        interval: 5000
        running: !root.finished
        repeat: false
        onTriggered: root.finish(false, "process timed out")
    }
}
