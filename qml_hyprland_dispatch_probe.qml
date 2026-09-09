import QtQuick
import Quickshell
import "qml" as Plugin

// Safe live-session probe for the Omarchy Lua dispatcher bridge. It focuses
// the already active workspace and does not launch, move, close, or resize a
// window. Run manually with: qs --no-color --path qml_hyprland_dispatch_probe.qml
ShellRoot {
    id: root

    property bool finished: false

    function finish(success, reason) {
        if (finished) return
        finished = true
        console.log("HYPRLAND_DISPATCH_PROBE=" + JSON.stringify({ success: success, reason: reason }))
        Qt.quit()
    }

    Plugin.BridgeProbe {
        id: bridgeProbe
        attestationHelper: {
            const encoded = String(Qt.resolvedUrl("backend/bridge_attestation.py"))
            const prefix = "file://"
            return encoded.startsWith(prefix) ? decodeURIComponent(encoded.slice(prefix.length)) : ""
        }
        onProbeFinished: function(success, reason) { root.finish(success, reason) }
    }

    Component.onCompleted: bridgeProbe.start()
}
