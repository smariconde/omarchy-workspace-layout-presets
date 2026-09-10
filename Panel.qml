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
    property var captureReview: null
    property var captureAssignments: ({})
    property int captureSelectionRevision: 0
    property bool confirmDelete: false
    property string statusText: ""

    readonly property int panelWidth: Style.space(410)
    readonly property int detailsListHeight: Math.min(
        Style.space(128), root.selectedProfileDetails.length * Style.space(18))
    implicitWidth: panelWidth
    implicitHeight: popup.contentHeight

    Plugin.LayoutctlClient { id: client }

    function messageFrom(response, fallback) {
        if (response && response.blocked && response.blocked.length)
            return friendlyIssue(response.blocked[0].code, fallback)
        if (response && response.error)
            return friendlyIssue(response.error.code, fallback)
        return fallback
    }
    function friendlyIssue(code, fallback) {
        switch (code) {
        case "workspace_not_empty": return "This workspace must be empty."
        case "unsupported_workspace": return "Switch to a regular workspace."
        case "nothing_to_restore": return "No apps in this preset can be opened."
        case "already_exists": return "A preset with this name already exists."
        case "plan_profile_mismatch":
        case "profile_changed":
        case "target_changed": return "This preview is no longer current. Open it again."
        case "unsupported_hyprland":
        case "unsupported_layout":
        case "dispatch_unverified": return "Restore isn't available right now."
        case "monitor_unavailable": return "Couldn't identify the current screen."
        case "capture_error": return "Couldn't save this workspace."
        case "plan_error": return "Couldn't prepare this preset."
        case "restore_error":
        case "replay_error": return "Couldn't restore this preset."
        case "profile_error": return "This preset can't be used."
        case "hyprland_error": return "Couldn't read the current workspace."
        case "storage_error": return "Couldn't access saved presets."
        default: return fallback
        }
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
        if (!action()) statusText = "Please wait."
        else statusText = text
    }
    function cancelCaptureReview() {
        captureReview = null
        captureAssignments = ({})
        captureSelectionRevision++
        statusText = "Capture cancelled. No preset was saved."
    }
    function captureOptions(review) {
        let options = [{ value: "", label: "Choose app…" },
                       { value: "../omit", label: "Do not restore this window" }]
        for (let candidate of review.candidates || [])
            options.push({ value: candidate.desktopId, label: candidate.displayName })
        return options
    }
    function allCaptureChoicesMade() {
        captureSelectionRevision
        if (!captureReview || !captureReview.review) return false
        for (let review of captureReview.review)
            if (!captureAssignments[review.nodeId]) return false
        return true
    }
    function commitCaptureReview() {
        if (!allCaptureChoicesMade()) {
            statusText = "Choose an app for every browser window."
            return
        }
        let choices = ({})
        for (let review of captureReview.review) {
            let value = captureAssignments[review.nodeId]
            choices[review.nodeId] = value === "../omit" ? null : value
        }
        runAction(function() {
            return client.commitCapture(captureReview.captureId, choices)
        }, "Saving reviewed preset…")
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
                        ? ""
                        : "No saved presets yet."
                } else root.statusText = root.messageFrom(response, "Couldn't load presets.")
                return
            }
            if (response && response.status === "ok") {
                if (operation === "capture-prepare") {
                    if (response.data.saved) {
                        root.captureReview = null
                        root.captureAssignments = ({})
                        captureName.text = ""
                        root.statusText = "Preset saved."
                        root.refresh()
                    } else {
                        root.captureReview = response.data
                        let initial = ({})
                        for (let review of response.data.review || [])
                            initial[review.nodeId] = review.suggestedDesktopId || ""
                        root.captureAssignments = initial
                        root.captureSelectionRevision++
                        root.statusText = "Choose the matching app."
                    }
                    return
                }
                if (operation === "capture-commit") {
                    root.captureReview = null
                    root.captureAssignments = ({})
                    captureName.text = ""
                    root.statusText = "Preset saved."
                    root.refresh()
                    return
                }
                if (operation === "profile-show") {
                    root.selectedProfileData = response.data.profile
                    root.selectedProfileDetails = response.data.details || []
                }
                if (operation === "plan") {
                    var preview = response.data
                    preview.warnings = response.warnings || []
                    root.planData = preview
                }
                if (operation === "profile-rename"
                        || operation === "profile-duplicate" || operation === "profile-delete"
                        || operation === "profile-import") {
                    if (operation === "profile-delete") {
                        root.clearSelection()
                    }
                        root.statusText = "Operation completed successfully."
                    root.refresh()
                }
                if (operation === "restore") {
                    const verification = response.data.verification || {}
                    const expected = verification.expected
                    const matched = verification.matched
                    if (response.data.failures && response.data.failures.length) {
                        root.statusText = Number.isInteger(expected) && Number.isInteger(matched)
                            ? (matched + " of " + expected + " apps restored.")
                            : "Some apps couldn't be restored."
                    } else {
                        root.statusText = Number.isInteger(matched)
                            ? (matched + (matched === 1 ? " app restored." : " apps restored."))
                            : "Preset restored."
                    }
                    root.planData = null
                }
            } else {
                root.statusText = root.messageFrom(response, "Couldn't complete that action.")
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
                        text: "Save or restore this workspace."
                        color: Color.popups.text
                        opacity: 0.58
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                    }
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
                        enabled: root.captureReview === null
                        onAccepted: saveButton.clicked()
                    }
                    Ui.Button {
                        id: saveButton
                        width: Style.space(142)
                        height: Style.spacing.controlHeight
                        text: "Save"
                        enabled: root.captureReview === null
                        foreground: Color.accent
                        bordered: true
                        onClicked: {
                            if (!captureName.text.trim()) {
                                root.statusText = "Enter a preset name."
                                captureName.forceActiveFocus()
                                return
                            }
                            root.runAction(function() { return client.capture(captureName.text.trim()) }, "Saving preset…")
                        }
                    }
                }

                Ui.BorderSurface {
                    visible: root.captureReview !== null
                    width: parent.width
                    height: root.captureReview
                        ? Style.space(122) + root.captureReview.review.length * Style.space(72) : 0
                    color: Util.alpha(Color.accent, 0.08)
                    borderSpec: Border.flat(Util.alpha(Color.accent, 0.58), Style.normalBorderWidth)
                    radius: Style.cornerRadius

                    Column {
                        anchors.fill: parent
                        anchors.margins: Style.spacing.sm
                        spacing: Style.spacing.xs

                        Text {
                            width: parent.width
                            text: "Choose an app"
                            color: Color.popups.text
                            font.family: Style.font.family
                            font.pixelSize: Style.font.body
                            font.weight: Font.Medium
                        }
                        Text {
                            width: parent.width
                            text: "Choose what should open for each browser window."
                            color: Color.popups.text
                            opacity: 0.66
                            wrapMode: Text.WordWrap
                            font.family: Style.font.family
                            font.pixelSize: Style.font.caption
                        }

                        Repeater {
                            model: root.captureReview ? root.captureReview.review : []
                            delegate: Column {
                                required property var modelData
                                width: parent.width
                                spacing: Style.spacing.xxs
                                Text {
                                    width: parent.width
                                    text: {
                                        return modelData.title || ("Browser window " + modelData.ordinal)
                                    }
                                    textFormat: Text.PlainText
                                    color: Color.popups.text
                                    opacity: 0.76
                                    elide: Text.ElideRight
                                    font.family: Style.font.family
                                    font.pixelSize: Style.font.caption
                                }
                                Ui.SearchableDropdown {
                                    width: parent.width
                                    height: Style.spacing.controlHeight
                                    showLabel: false
                                    placeholderText: "Search installed apps…"
                                    emptyText: "No matching app"
                                    options: root.captureOptions(modelData)
                                    value: root.captureAssignments[modelData.nodeId] || ""
                                    onChanged: function(value) {
                                        let updated = Object.assign({}, root.captureAssignments)
                                        updated[modelData.nodeId] = value
                                        root.captureAssignments = updated
                                        root.captureSelectionRevision++
                                    }
                                }
                            }
                        }

                        Row {
                            width: parent.width
                            spacing: Style.spacing.xs
                            Ui.Button {
                                width: (parent.width - parent.spacing) / 2
                                height: Style.spacing.controlHeight
                                text: "Cancel"
                                bordered: true
                                onClicked: root.cancelCaptureReview()
                            }
                            Ui.Button {
                                width: (parent.width - parent.spacing) / 2
                                height: Style.spacing.controlHeight
                                text: "Save preset"
                                enabled: root.allCaptureChoicesMade() && !client.running
                                bordered: true
                                foreground: Color.accent
                                onClicked: root.commitCaptureReview()
                            }
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
                        text: "Restore…"
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
                    height: root.planData ? Style.space(116) : 0
                    plan: root.planData
                    busy: client.running
                    onRestoreRequested: root.runAction(
                        function() { return client.restore(root.planData.planId) },
                        "Restoring…")
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
                                ? (root.selectedProfileData.name + " · "
                                   + (root.selectedProfileData.tiled.nodes.length
                                      + root.selectedProfileData.floating.length)
                                   + ((root.selectedProfileData.tiled.nodes.length
                                       + root.selectedProfileData.floating.length) === 1 ? " app" : " apps"))
                                : ""
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            color: Color.popups.text
                            opacity: 0.66
                            font.family: Style.font.family
                            font.pixelSize: Style.font.caption
                            text: root.selectedProfileData ? "Apps in this preset" : ""
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
                                        ? metadata.displayName : "Unavailable app"
                                    return name
                                }
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: root.statusText
                    color: root.statusText.indexOf("Couldn't") >= 0 || root.statusText.indexOf("must be") >= 0
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
