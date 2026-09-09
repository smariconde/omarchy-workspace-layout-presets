import QtQuick
import qs.Commons
import qs.Ui as Ui
import "qml" as Plugin

Ui.Panel {
    id: root
    moduleName: "santiago.workspace-layout-presets"
    ipcTarget: "santiago.workspace-layout-presets"
    manageIpc: false

    property var anchorItem: null
    property var hostWidget: null
    readonly property var barIdentity: hostWidget || root
    property var profiles: []
    property string selectedProfile: ""
    property var selectedProfileData: null
    property var selectedProfileDetails: []
    property var planData: null
    property bool confirmDelete: false
    property string statusText: ""

    readonly property int panelWidth: Style.space(410)
    readonly property int detailsListHeight: Math.min(
        Style.space(128), root.selectedProfileDetails.length * Style.space(18))
    implicitWidth: panelWidth
    implicitHeight: popup.contentHeight

    Plugin.LayoutctlClient { id: client }

    function messageFrom(response, fallback) {
        if (response && response.error && response.error.message) return response.error.message
        if (response && response.blocked && response.blocked.length) return response.blocked[0].message
        return fallback
    }
    function refresh() {
        if (!client.listProfiles()) return false
        statusText = "Loading presets…"
        return true
    }
    function clearSelection() {
        selectedProfile = ""
        selectedProfileData = null
        selectedProfileDetails = []
        planData = null
        confirmDelete = false
    }
    function choose(profileId) {
        selectedProfile = profileId
        selectedProfileData = null
        selectedProfileDetails = []
        planData = null
        confirmDelete = false
        client.showProfile(profileId)
    }
    function runAction(action, text) {
        if (!action()) statusText = "The backend is busy."
        else statusText = text
    }

    Connections {
        target: client
        function onCommandFinished(operation, exitCode, response, stderrText) {
            if (operation === "profile-list") {
                if (response && response.status === "ok") {
                    const profiles = response.data.profiles || []
                    root.profiles = profiles
                    if (root.selectedProfile !== "" && profiles.indexOf(root.selectedProfile) < 0)
                        root.clearSelection()
                    root.statusText = root.profiles.length
                        ? "Select a preset to see its details and actions."
                        : "No saved presets yet."
                } else root.statusText = root.messageFrom(response, stderrText || "Could not list presets.")
                return
            }
            if (response && response.status === "ok") {
                if (operation === "profile-show") {
                    root.selectedProfileData = response.data.profile
                    root.selectedProfileDetails = response.data.details || []
                }
                if (operation === "plan") {
                    var preview = response.data
                    preview.warnings = response.warnings || []
                    root.planData = preview
                }
                if (operation === "capture" || operation === "profile-rename"
                        || operation === "profile-duplicate" || operation === "profile-delete"
                        || operation === "profile-import") {
                    if (operation === "profile-delete") {
                        root.clearSelection()
                    }
                        root.statusText = operation === "capture"
                            ? "Layout saved successfully."
                            : "Operation completed successfully."
                    root.refresh()
                }
                if (operation === "restore") {
                    root.statusText = response.data.failures && response.data.failures.length
                        ? "Partial restore: review the result."
                        : "Layout restored successfully."
                    root.planData = null
                }
            } else {
                root.statusText = root.messageFrom(response, stderrText || "The operation was blocked.")
                root.confirmDelete = false
            }
        }
    }

    Component.onCompleted: refresh()
    onOpenedChanged: if (opened) refresh()

    Ui.KeyboardPanel {
        id: popup
        anchorItem: root.anchorItem
        owner: root.barIdentity
        bar: root.bar
        open: root.opened
        centerOnBar: false
        contentWidth: popup.fittedContentWidth(root.panelWidth)
        contentHeight: popup.fittedContentHeight(contentColumn.implicitHeight, Style.space(600))

        Flickable {
            id: contentScroll
            anchors.fill: parent
            contentWidth: width
            contentHeight: contentColumn.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height

            Column {
                id: contentColumn
                width: parent.width
                spacing: Style.spacing.panelGap
                Column {
                    width: parent.width
                    spacing: Style.spacing.xxs
                    Text {
                        text: "Workspace presets"
                        color: Color.popups.text
                        font.family: Style.font.family
                        font.pixelSize: Style.font.heading
                        font.weight: Font.Medium
                    }
                    Text {
                        text: "For the active workspace"
                        color: Color.popups.text
                        opacity: 0.58
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                    }
                }

                Text {
                    width: parent.width
                    text: "Save and restore only in the active, empty workspace."
                    color: Color.popups.text
                    opacity: 0.66
                    wrapMode: Text.WordWrap
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                }
                Rectangle {
                    width: parent.width
                    height: Style.spacing.hairline
                    color: Util.alpha(Color.popups.text, 0.22)
                }

                Ui.PanelSectionHeader { text: "Save" }
                Row {
                    width: parent.width
                    spacing: Style.spacing.controlGap
                    Ui.TextField {
                        id: captureName
                        width: parent.width - saveButton.width - parent.spacing
                        height: Style.spacing.controlHeight
                        placeholderText: "Preset name"
                        selectByMouse: true
                        onAccepted: saveButton.clicked()
                    }
                    Ui.Button {
                        id: saveButton
                        width: Style.space(142)
                        height: Style.spacing.controlHeight
                        text: "Save"
                        foreground: Color.accent
                        bordered: true
                        onClicked: {
                            if (!captureName.text.trim()) {
                                root.statusText = "Enter a preset name."
                                captureName.forceActiveFocus()
                                return
                            }
                            root.runAction(function() { return client.capture(captureName.text.trim()) }, "Saving preset…")
                            captureName.text = ""
                        }
                    }
                }

                Ui.PanelSectionHeader { text: "Saved presets" }
                Ui.BorderSurface {
                    width: parent.width
                    height: Style.space(116)
                    color: Util.alpha(Color.popups.text, 0.035)
                    borderSpec: Border.flat(Util.alpha(Color.popups.text, 0.22), Style.normalBorderWidth)
                    radius: Style.cornerRadius
                    ListView {
                        id: profileView
                        anchors.fill: parent
                        anchors.margins: Style.spacing.xs
                        clip: true
                        spacing: Style.spacing.xxs
                        model: root.profiles
                        delegate: Ui.Button {
                            required property string modelData
                            width: profileView.width
                            height: Style.spacing.popupRowHeight
                            text: modelData
                            leftAlign: true
                            selected: modelData === root.selectedProfile
                            active: selected
                            hasCursor: selected
                            foreground: Color.popups.text
                            accent: Color.accent
                            onClicked: root.choose(modelData)
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: root.profiles.length === 0
                            text: "No saved presets yet"
                            color: Color.popups.text
                            opacity: 0.55
                            font.family: Style.font.family
                            font.pixelSize: Style.font.bodySmall
                        }
                    }
                }

                Row {
                    width: parent.width
                    spacing: Style.spacing.xs
                    Ui.Button {
                        width: (parent.width - parent.spacing) / 2
                        height: Style.spacing.controlHeight
                        text: "Use"
                        enabled: root.selectedProfile !== ""
                        bordered: true
                        foreground: Color.accent
                        onClicked: {
                            root.planData = null
                            client.plan(root.selectedProfile)
                            root.statusText = "Preparing preview…"
                        }
                    }
                    Ui.Button {
                        width: (parent.width - parent.spacing) / 2
                        height: Style.spacing.controlHeight
                        text: "Delete"
                        enabled: root.selectedProfile !== ""
                        foreground: Color.urgent
                        bordered: true
                        onClicked: root.confirmDelete = true
                    }
                }

                Ui.BorderSurface {
                    visible: root.confirmDelete
                    width: parent.width
                    height: root.confirmDelete ? Style.space(38) : 0
                    color: Util.alpha(Color.urgent, 0.12)
                    borderSpec: Border.flat(Util.alpha(Color.urgent, 0.62), Style.normalBorderWidth)
                    radius: Style.cornerRadius
                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: Style.spacing.sm
                        anchors.rightMargin: Style.spacing.xs
                        spacing: Style.spacing.sm
                        Text {
                            width: parent.width - deleteConfirmButton.width - parent.spacing
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Delete “" + root.selectedProfile + "”?"
                            color: Color.popups.text
                            elide: Text.ElideRight
                            font.family: Style.font.family
                            font.pixelSize: Style.font.bodySmall
                        }
                        Ui.Button {
                            id: deleteConfirmButton
                            width: Style.space(82)
                            height: Style.spacing.controlHeight
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Delete"
                            foreground: Color.urgent
                            onClicked: {
                                root.confirmDelete = false
                                client.remove(root.selectedProfile)
                            }
                        }
                    }
                }

                Plugin.RestorePreview {
                    width: parent.width
                    height: root.planData ? Style.space(132) : 0
                    plan: root.planData
                    busy: client.running
                    onRestoreRequested: root.runAction(
                        function() { return client.restore(root.planData.planId) },
                        "Verifying compatibility…")
                }

                Ui.BorderSurface {
                    visible: root.selectedProfileData !== null
                    width: parent.width
                    height: root.selectedProfileData
                        ? Style.space(52) + root.detailsListHeight : 0
                    color: Util.alpha(Color.popups.text, 0.035)
                    borderSpec: Border.flat(Util.alpha(Color.popups.text, 0.18), Style.normalBorderWidth)
                    radius: Style.cornerRadius
                    Column {
                        anchors.fill: parent
                        anchors.margins: Style.spacing.sm
                        spacing: Style.spacing.xxs
                        Text {
                            width: parent.width
                            color: Color.popups.text
                            font.family: Style.font.family
                            font.pixelSize: Style.font.caption
                            font.weight: Font.Medium
                            text: root.selectedProfileData
                                ? (root.selectedProfileData.name + " · " + root.selectedProfileData.layoutConfidence
                                   + " · workspace " + root.selectedProfileData.source.workspace.name
                                   + " · " + root.selectedProfileData.source.monitor.connector)
                                : ""
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            color: Color.popups.text
                            opacity: 0.66
                            font.family: Style.font.family
                            font.pixelSize: Style.font.caption
                            text: root.selectedProfileData
                                ? ("Tiled: " + root.selectedProfileData.tiled.nodes.length
                                   + " · Floating: " + root.selectedProfileData.floating.length)
                                : ""
                        }
                        ListView {
                            width: parent.width
                            height: root.detailsListHeight
                            clip: true
                            spacing: Style.spacing.xxs
                            model: root.selectedProfileDetails
                            delegate: Text {
                                required property var modelData
                                width: parent.width
                                color: Color.popups.text
                                opacity: 0.72
                                font.family: Style.font.family
                                font.pixelSize: Style.font.caption
                                elide: Text.ElideRight
                                text: {
                                    let metadata = modelData.metadata
                                    let name = metadata && metadata.displayName
                                        ? metadata.displayName : modelData.wmClass
                                    let kind = metadata && metadata.kind === "webapp"
                                        ? "Web app" : "Application"
                                    let category = metadata && metadata.categories && metadata.categories.length
                                        ? " · " + metadata.categories.join(", ") : ""
                                    return name + " · " + kind + category + " · " + modelData.placement
                                }
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: root.statusText
                    color: root.statusText.indexOf("blocked") >= 0 || root.statusText.indexOf("Could not") >= 0
                        ? Color.urgent : Color.popups.text
                    opacity: 0.75
                    wrapMode: Text.WordWrap
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
            }
        }
    }
}
