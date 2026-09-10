import QtQuick
import Quickshell.Io

// The sole QML-to-backend process boundary. It exposes narrowly scoped methods
// whose argv arrays are fixed in source; profile content never becomes shell
// source or an executable command.
Item {
    id: root

    readonly property string backendExecutable: localFilePath(Qt.resolvedUrl("../backend/layoutctl.py"))
    readonly property string attestationHelper: localFilePath(Qt.resolvedUrl("../backend/bridge_attestation.py"))
    readonly property bool running: process.running || bridgeProbe.running || pendingRestorePlanId.length > 0
    property string pendingOperation: ""
    property string pendingRestorePlanId: ""

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
        if (running || backendExecutable.length === 0) return false
        pendingOperation = operation
        process.command = [backendExecutable].concat(arguments)
        process.running = true
        return true
    }

    function showProfile(profileId) { return run("profile-show", ["profile", "show", profileId]) }
    function capture(name) { return run("capture-prepare", ["capture", "prepare", name]) }
    function commitCapture(captureId, assignments) {
        return run("capture-commit", ["capture", "commit", captureId, JSON.stringify(assignments)])
    }
    function plan(profileId) { return run("plan", ["plan", profileId]) }
    function restore(planId) {
        if (running || typeof planId !== "string" || planId.length === 0) return false
        pendingOperation = "restore"
        pendingRestorePlanId = planId
        if (!bridgeProbe.start()) {
            pendingOperation = ""
            pendingRestorePlanId = ""
            return false
        }
        return true
    }
    function rename(profileId, name) { return run("profile-rename", ["profile", "rename", profileId, name]) }
    function duplicate(profileId, newProfileId) { return run("profile-duplicate", ["profile", "duplicate", profileId, newProfileId]) }
    function remove(profileId) { return run("profile-delete", ["profile", "delete", profileId, "--confirm"]) }
    function exportProfile(profileId, destination) { return run("profile-export", ["profile", "export", profileId, destination]) }
    function importProfile(source) { return run("profile-import", ["profile", "import", source]) }

    BridgeProbe {
        id: bridgeProbe
        attestationHelper: root.attestationHelper

        onProbeFinished: function(success, reason) {
            if (!success) {
                const operation = root.pendingOperation
                root.pendingOperation = ""
                root.pendingRestorePlanId = ""
                root.commandFinished(operation, 1, {
                    contractVersion: 1,
                    status: "blocked",
                    data: null,
                    warnings: [],
                    blocked: [{ code: "dispatch_unverified", message: reason + " Nothing was restored." }],
                    error: null
                }, "")
                return
            }
            const planId = root.pendingRestorePlanId
            root.pendingRestorePlanId = ""
            process.command = [root.backendExecutable, "restore", planId]
            process.running = true
        }
    }

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
            const stderrText = stderr.text || ""
            root.pendingOperation = ""

            // Quickshell still reports Process.running=true while onExited is
            // executing. Defer notifications so handlers can safely enqueue
            // the next command (for example, refreshing after save/delete).
            Qt.callLater(function() {
                if (operation === "profile-list") root.profileListFinished(exitCode, response, stderrText)
                root.commandFinished(operation, exitCode, response, stderrText)
            })
        }
    }
}
