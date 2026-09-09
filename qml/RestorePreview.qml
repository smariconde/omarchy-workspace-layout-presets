import QtQuick
import qs.Commons
import qs.Ui as Ui

Item {
    id: root
    property var plan: null
    signal restoreRequested()
    visible: plan !== null

    Ui.BorderSurface {
        anchors.fill: parent
        color: Util.alpha(Color.accent, 0.06)
        borderSpec: Border.flat(Util.alpha(Color.accent, 0.5), Style.normalBorderWidth)
        radius: Style.cornerRadius

        Column {
            anchors.fill: parent
            anchors.margins: Style.spacing.sm
            spacing: Style.spacing.xs

            Row {
                width: parent.width
                spacing: Style.spacing.sm
                Text {
                    width: parent.width - previewMode.width - parent.spacing
                    text: root.plan ? "Restore preview" : ""
                    color: Color.popups.text
                    font.family: Style.font.family
                    font.pixelSize: Style.font.title
                    font.weight: Font.Medium
                    elide: Text.ElideRight
                }
                Text {
                    id: previewMode
                    text: root.plan ? root.plan.layoutMode : ""
                    color: Color.accent
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    font.weight: Font.Bold
                }
            }

            Text {
                width: parent.width
                text: root.plan
                    ? ("Launch " + root.plan.summary.launch + " · skip " + root.plan.summary.skip
                       + " · tiled " + root.plan.summary.tiled + " · floating " + root.plan.summary.floating)
                    : ""
                color: Color.popups.text
                opacity: 0.72
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                text: root.plan ? ("Workspace " + root.plan.target.workspace.name + " · " + root.plan.target.monitor.connector) : ""
                color: Color.popups.text
                opacity: 0.58
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
            }

            Row {
                width: parent.width
                spacing: Style.spacing.sm
                Text {
                    width: parent.width - restoreButton.width - parent.spacing
                    text: root.plan
                        ? ((root.plan.warnings && root.plan.warnings.length)
                           ? root.plan.warnings[0].message
                           : "Ready to restore in an empty workspace.")
                        : ""
                    color: root.plan && root.plan.warnings && root.plan.warnings.length
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
                    enabled: root.plan !== null
                    onClicked: root.restoreRequested()
                }
            }
        }
    }
}
