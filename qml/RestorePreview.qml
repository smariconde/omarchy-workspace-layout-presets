import QtQuick
import qs.Commons
import qs.Ui as Ui

Item {
    id: root
    property var plan: null
    property bool busy: false
    property double nowMillis: Date.now()
    readonly property bool expired: {
        if (!plan || typeof plan.expiresAt !== "string") return true
        const expiresAt = Date.parse(plan.expiresAt)
        return isNaN(expiresAt) || nowMillis >= expiresAt
    }
    signal restoreRequested()
    visible: plan !== null

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

    Timer {
        interval: 1000
        running: root.visible
        repeat: true
        onTriggered: root.nowMillis = Date.now()
    }

    Ui.BorderSurface {
        anchors.fill: parent
        color: Util.alpha(Color.accent, 0.06)
        borderSpec: Border.flat(Util.alpha(Color.accent, 0.5), Style.normalBorderWidth)
        radius: Style.cornerRadius

        Column {
            anchors.fill: parent
            anchors.margins: Style.spacing.sm
            spacing: Style.spacing.xs

            Text {
                width: parent.width
                text: root.plan ? ("Restore “" + root.plan.profileName + "”?") : ""
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.title
                font.weight: Font.Medium
                elide: Text.ElideRight
            }

            Text {
                width: parent.width
                text: root.plan
                    ? ("Opens " + root.plan.summary.launch
                       + (root.plan.summary.launch === 1 ? " app" : " apps")
                       + " in workspace " + root.plan.target.workspace.name + ".")
                    : ""
                color: Color.popups.text
                opacity: 0.72
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                elide: Text.ElideRight
            }
            Row {
                width: parent.width
                spacing: Style.spacing.sm
                Text {
                    width: parent.width - restoreButton.width - parent.spacing
                    text: root.plan
                        ? (root.expired
                           ? "Preview expired. Open it again."
                           : root.warningText())
                        : ""
                    color: root.expired || root.warningText().length
                        ? Color.accent : Color.popups.text
                    opacity: 0.78
                    wrapMode: Text.WordWrap
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                Ui.Button {
                    id: restoreButton
                    width: Style.space(112)
                    height: Style.spacing.controlHeight
                    text: "Restore"
                    foreground: Color.accent
                    bordered: true
                    enabled: root.plan !== null && !root.expired && !root.busy
                    onClicked: root.restoreRequested()
                }
            }
        }
    }
}
