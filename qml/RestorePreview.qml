import QtQuick
import qs.Commons
import qs.Ui as Ui

Item {
    id: root
    property var plan: null
    property bool busy: false
    property double nowMillis: Date.now()
    readonly property color secondaryText: Util.alpha(Color.popups.text, 0.72)
    readonly property bool expired: {
        if (!plan || typeof plan.expiresAt !== "string") return true
        const expiresAt = Date.parse(plan.expiresAt)
        return isNaN(expiresAt) || nowMillis >= expiresAt
    }
    readonly property string effectiveWarningText: !plan ? ""
        : expired ? "Preview expired. Open it again." : warningText()
    signal restoreRequested()
    visible: plan !== null
    implicitHeight: visible ? previewSurface.implicitHeight : 0
    height: implicitHeight

    function warningText() {
        if (!plan) return ""
        const skipped = plan.summary ? plan.summary.skip : 0
        if (skipped > 0)
            return skipped + (skipped === 1 ? " app won't be opened." : " apps won't be opened.")
        for (let warning of plan.warnings || []) {
            if (warning.code === "layout_fallback" || warning.code === "tree_incomplete")
                return "Window positions may vary."
            if (warning.code === "monitor_changed")
                return "Window sizes will adapt to this screen."
            if (warning.code === "duplicate_window")
                return "Repeated apps may open different content."
            if (warning.code === "geometry_clamped")
                return "Window sizes were adjusted to fit this screen."
        }
        return ""
    }

    onPlanChanged: nowMillis = Date.now()
    Timer { interval: 1000; running: root.visible; repeat: true
        onTriggered: root.nowMillis = Date.now() }

    Ui.BorderSurface {
        id: previewSurface
        width: parent.width
        padding: Style.spacing.xl
        implicitHeight: previewColumn.implicitHeight + contentTopInset + contentBottomInset
        height: implicitHeight
        color: Util.alpha(Color.accent, 0.06)
        borderSpec: Border.flat(Util.alpha(Color.accent, 0.5), Style.normalBorderWidth)
        radius: Style.cornerRadius

        Column {
            id: previewColumn
            width: parent.width - previewSurface.contentLeftInset - previewSurface.contentRightInset
            x: previewSurface.contentLeftInset
            y: previewSurface.contentTopInset
            spacing: Style.spacing.lg

            Text {
                id: previewTitle
                width: parent.width
                text: root.plan ? ("Restore “" + root.plan.profileName + "”?") : ""
                textFormat: Text.PlainText
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.title
                font.weight: Font.Medium
                elide: Text.ElideRight
                MouseArea { id: titleHover; anchors.fill: parent
                    acceptedButtons: Qt.NoButton; hoverEnabled: true }
                Ui.PanelToolTip { visible: previewTitle.truncated && titleHover.containsMouse
                    text: root.plan ? root.plan.profileName : "" }
            }
            Text {
                width: parent.width
                text: root.plan ? ("Opens " + root.plan.summary.launch
                    + (root.plan.summary.launch === 1 ? " app" : " apps")
                    + " in workspace " + root.plan.target.workspace.name + ".") : ""
                textFormat: Text.PlainText
                color: root.secondaryText
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                visible: text.length > 0
                text: root.effectiveWarningText
                textFormat: Text.PlainText
                color: root.expired ? Color.urgent : Color.accent
                wrapMode: Text.WordWrap
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Item {
                width: parent.width
                height: Style.spacing.controlHeight
                Ui.Button {
                    anchors.right: parent.right
                    width: Style.space(112)
                    height: Style.spacing.controlHeight
                    text: "Restore"
                    focusable: true
                    foreground: Color.accent
                    bordered: true
                    enabled: root.plan !== null && !root.expired && !root.busy
                    onClicked: root.restoreRequested()
                }
            }
        }
    }
}
