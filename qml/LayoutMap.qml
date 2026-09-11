import QtQuick
import qs.Commons

// A wordless sketch of a saved workspace: one cell per window, drawn at the
// proportions the profile recorded. It carries no labels on purpose — the
// shape alone should answer "how would my screen look?" at a glance. The
// backend resolves every rectangle; this file only paints them.
Item {
    id: root

    property var layout: null
    readonly property var tiledWindows: root.windowsFor("tiled")
    readonly property var floatingWindows: root.windowsFor("floating")
    readonly property bool hasLayout: tiledWindows.length > 0 || floatingWindows.length > 0
    readonly property bool approximate: layout && layout.mode === "approximate"

    // Keep the sketch shaped like the screen the preset was captured on.
    readonly property real aspectRatio: {
        const aspect = layout ? layout.aspect : null
        if (!aspect || !(aspect.width > 0) || !(aspect.height > 0)) return 9 / 16
        return aspect.height / aspect.width
    }
    readonly property int gap: Style.spacing.xxs

    visible: hasLayout
    implicitHeight: visible ? frame.height + (approximate ? caption.height + Style.spacing.xs : 0) : 0
    height: implicitHeight

    function windowsFor(placement) {
        if (!layout || !layout.windows) return []
        return layout.windows.filter(function (window) { return window.placement === placement })
    }

    component Cell: Rectangle {
        required property var modelData
        readonly property real minSide: Math.min(width, height)
        x: frame.pad + modelData.x * frame.innerWidth + root.gap / 2
        y: frame.pad + modelData.y * frame.innerHeight + root.gap / 2
        width: Math.max(1, modelData.width * frame.innerWidth - root.gap)
        height: Math.max(1, modelData.height * frame.innerHeight - root.gap)
        // Miniature cells need a gentler corner than a full-size window.
        radius: Math.min(Style.cornerRadius, minSide / 4, Style.space(4))
        border.width: Style.normalBorderWidth
    }

    Rectangle {
        id: frame
        width: root.width
        height: Math.round(root.width * root.aspectRatio)
        radius: Style.cornerRadius
        color: Util.alpha(Color.popups.text, 0.06)
        border.width: Style.normalBorderWidth
        border.color: Util.alpha(Color.popups.text, 0.18)

        readonly property int pad: root.gap
        readonly property real innerWidth: Math.max(0, width - pad * 2)
        readonly property real innerHeight: Math.max(0, height - pad * 2)

        Repeater {
            model: root.tiledWindows
            Cell {
                color: root.approximate
                    ? Util.alpha(Color.popups.text, 0.14)
                    : Util.alpha(Color.accent, 0.20)
                border.color: root.approximate
                    ? Util.alpha(Color.popups.text, 0.28)
                    : Util.alpha(Color.accent, 0.55)
            }
        }

        // Floating windows sit above the tiled ones, as they do on the desktop.
        Repeater {
            model: root.floatingWindows
            Cell {
                color: Util.alpha(Color.accent, 0.40)
                border.color: Util.alpha(Color.accent, 0.75)
            }
        }
    }

    Text {
        id: caption
        anchors.top: frame.bottom
        anchors.topMargin: Style.spacing.xs
        width: root.width
        visible: root.approximate
        // The stored splits were never measured, so the cells above are a
        // placeholder. Say so rather than let evenly sized cells imply a shape.
        text: "Approximate layout."
        textFormat: Text.PlainText
        color: Util.alpha(Color.popups.text, 0.58)
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }
}
