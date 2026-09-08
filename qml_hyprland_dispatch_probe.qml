import QtQuick
import Quickshell
import Quickshell.Io

// Safe live-session probe for the Omarchy Lua dispatcher bridge. It focuses
// the already active workspace and does not launch, move, close, or resize a
// window. Run manually with: qs --no-color --path qml_hyprland_dispatch_probe.qml
ShellRoot {
    id: root

    property bool finished: false

    function localFilePath(url) {
        const encoded = String(url)
        const filePrefix = "file://"
        if (!encoded.startsWith(filePrefix)) return ""
        return decodeURIComponent(encoded.slice(filePrefix.length))
    }

    function finish(success, reason) {
        if (finished) return
        finished = true
        console.log("HYPRLAND_DISPATCH_PROBE=" + JSON.stringify({ success: success, reason: reason }))
        Qt.quit()
    }

    Process {
        id: workspaceProcess
        command: ["hyprctl", "-j", "activeworkspace"]

        stdout: StdioCollector { id: workspaceStdout; waitForEnd: true }
        stderr: StdioCollector { id: workspaceStderr; waitForEnd: true }

        onExited: function(exitCode) {
            if (exitCode !== 0 || (workspaceStdout.text || "").trim().length === 0) {
                root.finish(false, "activeworkspace query failed")
                return
            }

            let workspace = null
            try {
                workspace = JSON.parse(workspaceStdout.text)
            } catch (error) {
                root.finish(false, "activeworkspace returned invalid JSON")
                return
            }

            if (!workspace || !Number.isInteger(workspace.id) || workspace.id <= 0) {
                root.finish(false, "active workspace id is invalid")
                return
            }

            // The third argv item is one dispatcher expression. No shell is
            // involved, and the only interpolated value is a validated integer.
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
            const output = (dispatchStdout.text || "") + (dispatchStderr.text || "")
            if (exitCode !== 0) {
                root.finish(false, "dispatch failed: " + output.trim())
                return
            }
            const workspace = JSON.parse(workspaceStdout.text)
            attestationProcess.command = [
                "python3",
                root.localFilePath(Qt.resolvedUrl("backend/bridge_attestation.py")),
                "record",
                String(workspace.id)
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
            const output = (attestationStdout.text || "").trim()
            if (exitCode !== 0) {
                root.finish(false, "attestation failed: " + output + " " + (attestationStderr.text || "").trim())
                return
            }
            let record = null
            try {
                record = JSON.parse(output)
            } catch (error) {
                root.finish(false, "attestation returned invalid JSON")
                return
            }
            root.finish(record !== null && record.schemaVersion === 1, "ok")
        }
    }

    Component.onCompleted: workspaceProcess.running = true

    Timer {
        interval: 5000
        running: !root.finished
        repeat: false
        onTriggered: root.finish(false, "probe timed out")
    }
}
