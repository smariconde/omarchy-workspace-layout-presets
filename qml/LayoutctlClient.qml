import QtQuick
import Quickshell.Io

// The sole QML-to-backend process boundary. It exposes narrowly scoped methods
// whose argv arrays are fixed in source; profile content never becomes shell
// source or an executable command.
QtObject {
    id: root

    readonly property string backendExecutable: localFilePath(Qt.resolvedUrl("../backend/layoutctl.py"))
    readonly property bool running: profileListProcess.running

    signal profileListFinished(int exitCode, var response, string stderrText)

    function localFilePath(url) {
        const encoded = String(url)
        const filePrefix = "file://"
        if (!encoded.startsWith(filePrefix)) return ""
        return decodeURIComponent(encoded.slice(filePrefix.length))
    }

    function listProfiles() {
        if (profileListProcess.running || backendExecutable.length === 0) return false
        profileListProcess.command = [backendExecutable, "profile", "list"]
        profileListProcess.running = true
        return true
    }

    property Process profileListProcess: Process {
        id: profileListProcess
        running: false
        command: []

        stdout: StdioCollector {
            id: profileListStdout
            waitForEnd: true
        }

        stderr: StdioCollector {
            id: profileListStderr
            waitForEnd: true
        }

        onExited: function(exitCode) {
            let response = null
            try {
                response = JSON.parse(profileListStdout.text || "")
            } catch (error) {
                response = null
            }
            root.profileListFinished(exitCode, response, profileListStderr.text || "")
        }
    }
}
