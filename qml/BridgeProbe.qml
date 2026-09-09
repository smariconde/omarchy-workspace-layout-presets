import QtQuick
import Quickshell.Io

// Verify the exact Omarchy Lua dispatcher immediately before a restore.
// The only state-changing probe focuses the already active workspace.
Item {
    id: root

    required property string attestationHelper
    readonly property bool running: workspaceProcess.running
        || dispatchProcess.running || attestationProcess.running
    property int workspaceId: 0
    property bool active: false

    signal probeFinished(bool success, string reason)

    function start() {
        if (running || active || attestationHelper.length === 0) return false
        active = true
        workspaceId = 0
        timeout.restart()
        workspaceProcess.command = ["hyprctl", "-j", "activeworkspace"]
        workspaceProcess.running = true
        return true
    }

    function finish(success, reason) {
        if (!active) return
        active = false
        timeout.stop()
        probeFinished(success, reason)
    }

    Process {
        id: workspaceProcess
        command: []
        stdout: StdioCollector { id: workspaceStdout; waitForEnd: true }
        stderr: StdioCollector { id: workspaceStderr; waitForEnd: true }

        onExited: function(exitCode) {
            if (!root.active) return
            if (exitCode !== 0 || (workspaceStdout.text || "").trim().length === 0) {
                root.finish(false, "Could not read the active workspace.")
                return
            }
            let workspace = null
            try {
                workspace = JSON.parse(workspaceStdout.text)
            } catch (error) {
                root.finish(false, "Hyprland returned an invalid active workspace.")
                return
            }
            if (!workspace || !Number.isInteger(workspace.id) || workspace.id <= 0) {
                root.finish(false, "Restore requires a regular active workspace.")
                return
            }

            root.workspaceId = workspace.id
            dispatchProcess.command = [
                "hyprctl",
                "dispatch",
                "hl.dsp.focus({ workspace = " + workspace.id + " })"
            ]
            dispatchProcess.running = true
        }
    }

    Process {
        id: dispatchProcess
        command: []
        stdout: StdioCollector { id: dispatchStdout; waitForEnd: true }
        stderr: StdioCollector { id: dispatchStderr; waitForEnd: true }

        onExited: function(exitCode) {
            if (!root.active) return
            if (exitCode !== 0) {
                root.finish(false, "The Hyprland restore bridge is unavailable.")
                return
            }
            attestationProcess.command = [
                "python3",
                root.attestationHelper,
                "record",
                String(root.workspaceId)
            ]
            attestationProcess.running = true
        }
    }

    Process {
        id: attestationProcess
        command: []
        stdout: StdioCollector { id: attestationStdout; waitForEnd: true }
        stderr: StdioCollector { id: attestationStderr; waitForEnd: true }

        onExited: function(exitCode) {
            if (!root.active) return
            const output = (attestationStdout.text || "").trim()
            if (exitCode !== 0) {
                root.finish(false, "Could not verify Hyprland compatibility.")
                return
            }
            let record = null
            try {
                record = JSON.parse(output)
            } catch (error) {
                root.finish(false, "The compatibility check returned invalid data.")
                return
            }
            if (!record || record.schemaVersion !== 1 || record.workspaceId !== root.workspaceId) {
                root.finish(false, "The compatibility check could not be trusted.")
                return
            }
            root.finish(true, "ok")
        }
    }

    Timer {
        id: timeout
        interval: 5000
        repeat: false
        onTriggered: root.finish(false, "The Hyprland compatibility check timed out.")
    }
}
