import QtQuick
import Quickshell.Io

// The sole QML-to-backend process boundary. It exposes narrowly scoped methods
// whose argv arrays are fixed in source; profile content never becomes shell
// source or an executable command.
Item {
    id: root

    readonly property string backendExecutable: localFilePath(Qt.resolvedUrl("../backend/layoutctl.py"))
    readonly property bool running: process.running
    property string pendingOperation: ""

    signal profileListFinished(int exitCode, var response, string stderrText)
    signal commandFinished(string operation, int exitCode, var response, string stderrText)

    function localFilePath(url) {
        const encoded = String(url)
        const filePrefix = "file://"
        if (!encoded.startsWith(filePrefix)) return ""
        return decodeURIComponent(encoded.slice(filePrefix.length))
    }

    function listProfiles() {
        return run("profile-list", ["profile", "list"])
    }

    function run(operation, arguments) {
        if (process.running || backendExecutable.length === 0) return false
        pendingOperation = operation
        process.command = [backendExecutable].concat(arguments)
        process.running = true
        return true
    }

    function showProfile(profileId) { return run("profile-show", ["profile", "show", profileId]) }
    function capture(name) { return run("capture", ["capture", name]) }
    function plan(profileId) { return run("plan", ["plan", profileId]) }
    function restore(planId) { return run("restore", ["restore", planId]) }
    function rename(profileId, name) { return run("profile-rename", ["profile", "rename", profileId, name]) }
    function duplicate(profileId, newProfileId) { return run("profile-duplicate", ["profile", "duplicate", profileId, newProfileId]) }
    function remove(profileId) { return run("profile-delete", ["profile", "delete", profileId, "--confirm"]) }
    function exportProfile(profileId, destination) { return run("profile-export", ["profile", "export", profileId, destination]) }
    function importProfile(source) { return run("profile-import", ["profile", "import", source]) }

    Process {
        id: process
        running: false
        command: []

        stdout: StdioCollector {
            id: stdout
            waitForEnd: true
        }

        stderr: StdioCollector {
            id: stderr
            waitForEnd: true
        }

        onExited: function(exitCode) {
            let response = null
            try {
                response = JSON.parse(stdout.text || "")
            } catch (error) {
                response = null
            }
            const operation = root.pendingOperation
            root.pendingOperation = ""
            if (operation === "profile-list") root.profileListFinished(exitCode, response, stderr.text || "")
            root.commandFinished(operation, exitCode, response, stderr.text || "")
        }
    }
}
