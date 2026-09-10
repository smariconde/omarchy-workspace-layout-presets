import QtQuick
import qs.Ui

// Omarchy bar-widget contract: the root inherits BarWidget and the visible
// affordance is a BarIconButton. The panel is hosted by KeyboardPanel so it is
// positioned and focused like every other Omarchy shell popup.
BarWidget {
    id: root
    moduleName: "io.github.smariconde.workspace-layout-presets"

    readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
    // Keep the host bar's open-panel mark aligned with the glyph's optically
    // centered painted bounds instead of sizing it from the whole slot.
    readonly property real openPanelIndicatorWidth: button.glyphPaintedWidth

    function open() { if (panelLoader.item) panelLoader.item.open() }
    function close() { if (panelLoader.item) panelLoader.item.close() }
    function togglePanel() { if (panelLoader.item) panelLoader.item.toggle() }
    function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    onBarChanged: injectPanel()
    onSettingsChanged: injectPanel()

    function injectPanel() {
        var target = panelLoader.item
        if (!target) return
        if ("bar" in target) target.bar = root.bar
        if ("settings" in target) target.settings = root.settings
        if ("anchorItem" in target) target.anchorItem = button
        if ("hostWidget" in target) target.hostWidget = root
        if ("pluginVersion" in target && root.manifest && root.manifest.version)
            target.pluginVersion = root.manifest.version
    }

    Loader {
        id: panelLoader
        active: true
        source: Qt.resolvedUrl("Panel.qml")
        visible: false
        onLoaded: {
            root.injectPanel()
            Qt.callLater(root.injectPanel)
        }
    }

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        // Nerd Fonts' view-dashboard mark reads as an asymmetric tiled layout.
        text: "\udb81\udd6e"
        tooltipText: "Workspace layouts"
        onPressed: function(buttonCode) {
            if (buttonCode === Qt.LeftButton) root.togglePanel()
        }
    }
}
