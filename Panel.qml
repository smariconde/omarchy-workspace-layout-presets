import QtQuick
import QtQuick.Controls
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
    property string statusKind: "neutral"
    property bool preserveFeedbackOnList: false

    readonly property int panelWidth: Style.space(380)
    readonly property color secondaryText: Util.alpha(Color.popups.text, 0.72)
    readonly property color mutedText: Util.alpha(Color.popups.text, 0.58)
    readonly property int profileRowHeight: Style.spacing.popupRowHeight
    readonly property int visibleProfileRows: Math.min(5, profiles.length)
    readonly property int profileRowsHeight: visibleProfileRows > 0
        ? visibleProfileRows * profileRowHeight + (visibleProfileRows - 1) * Style.spacing.xxs
        : Style.space(40)
    readonly property int detailRowHeight: Math.ceil(detailMetrics.height + Style.spacing.md)
    readonly property int visibleDetailRows: Math.min(5, selectedProfileDetails.length)
    readonly property int detailsListHeight: visibleDetailRows > 0
        ? visibleDetailRows * detailRowHeight + (visibleDetailRows - 1) * Style.spacing.xxs : 0
    readonly property color statusColor: statusKind === "error" ? Color.urgent
        : statusKind === "progress" || statusKind === "success" ? Color.accent : secondaryText
    implicitWidth: panelWidth
    implicitHeight: popup.contentHeight

    FontMetrics { id: detailMetrics; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
    Plugin.LayoutctlClient { id: client }

    function setStatus(kind, message) { statusKind = kind; statusText = message }
    function messageFrom(response, fallback) {
        if (response && response.blocked && response.blocked.length)
            return friendlyIssue(response.blocked[0].code, fallback)
        if (response && response.error) return friendlyIssue(response.error.code, fallback)
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
    function refresh(preserveFeedback) {
        if (!client.listProfiles()) {
            if (!preserveFeedback) setStatus("neutral", "Please wait.")
            return false
        }
        preserveFeedbackOnList = preserveFeedback === true
        if (!preserveFeedbackOnList) setStatus("progress", "Loading presets…")
        return true
    }
    function clearSelection() {
        selectedProfile = ""; selectedProfileData = null; selectedProfileDetails = []
        planData = null; confirmDelete = false
    }
    function runAction(action, text) {
        if (!action()) setStatus("neutral", "Please wait.")
        else setStatus("progress", text)
    }
    function choose(profileId) {
        if (client.running) return
        selectedProfile = profileId; selectedProfileData = null; selectedProfileDetails = []
        planData = null; confirmDelete = false
        runAction(function() { return client.showProfile(profileId) }, "Loading preset…")
    }
    function cancelCaptureReview() {
        captureReview = null; captureAssignments = ({}); captureSelectionRevision++
        setStatus("neutral", "Capture cancelled. No preset was saved.")
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
            setStatus("error", "Choose an app for every browser window."); return
        }
        let choices = ({})
        for (let review of captureReview.review) {
            let value = captureAssignments[review.nodeId]
            choices[review.nodeId] = value === "../omit" ? null : value
        }
        runAction(function() { return client.commitCapture(captureReview.captureId, choices) },
                  "Saving reviewed preset…")
    }

    Connections {
        target: client
        function onCommandFinished(operation, exitCode, response, stderrText) {
            if (operation === "profile-list") {
                if (response && response.status === "ok") {
                    const listed = response.data.profiles || []
                    root.profiles = listed
                    if (root.selectedProfile !== "" && listed.indexOf(root.selectedProfile) < 0)
                        root.clearSelection()
                    if (!root.preserveFeedbackOnList) root.setStatus("neutral", "")
                } else root.setStatus("error", root.messageFrom(response, "Couldn't load presets."))
                root.preserveFeedbackOnList = false
                return
            }
            if (response && response.status === "ok") {
                if (operation === "capture-prepare") {
                    if (response.data.saved) {
                        root.captureReview = null; root.captureAssignments = ({}); captureName.text = ""
                        root.setStatus("success", "Preset saved."); root.refresh(true)
                    } else {
                        root.captureReview = response.data
                        let initial = ({})
                        for (let review of response.data.review || [])
                            initial[review.nodeId] = review.suggestedDesktopId || ""
                        root.captureAssignments = initial; root.captureSelectionRevision++
                        root.setStatus("neutral", "")
                    }
                    return
                }
                if (operation === "capture-commit") {
                    root.captureReview = null; root.captureAssignments = ({}); captureName.text = ""
                    root.setStatus("success", "Preset saved."); root.refresh(true); return
                }
                if (operation === "profile-show") {
                    root.selectedProfileData = response.data.profile
                    root.selectedProfileDetails = response.data.details || []
                    root.setStatus("neutral", "")
                }
                if (operation === "plan") {
                    var preview = response.data; preview.warnings = response.warnings || []
                    root.planData = preview; root.setStatus("neutral", "")
                }
                if (operation === "profile-rename" || operation === "profile-duplicate"
                        || operation === "profile-delete" || operation === "profile-import") {
                    if (operation === "profile-delete") root.clearSelection()
                    root.setStatus("success", operation === "profile-delete"
                        ? "Preset deleted." : "Operation completed successfully.")
                    root.refresh(true)
                }
                if (operation === "restore") {
                    const verification = response.data.verification || {}
                    const expected = verification.expected; const matched = verification.matched
                    if (response.data.failures && response.data.failures.length)
                        root.setStatus("error", Number.isInteger(expected) && Number.isInteger(matched)
                            ? matched + " of " + expected + " apps restored."
                            : "Some apps couldn't be restored.")
                    else root.setStatus("success", Number.isInteger(matched)
                        ? matched + (matched === 1 ? " app restored." : " apps restored.")
                        : "Preset restored.")
                    root.planData = null
                }
            } else {
                root.setStatus("error", root.messageFrom(response, "Couldn't complete that action."))
                root.confirmDelete = false
            }
        }
    }

    Component.onCompleted: refresh(false)
    onOpenedChanged: if (opened) refresh(false)

    Ui.KeyboardPanel {
        id: popup
        anchorItem: root.anchorItem; owner: root.barIdentity; bar: root.bar
        open: root.opened; centerOnBar: false
        focusTarget: captureName.enabled ? captureName : panelFocusScope
        contentWidth: popup.fittedContentWidth(root.panelWidth)
        contentHeight: popup.fittedContentHeight(contentColumn.implicitHeight, Style.space(600))

        FocusScope {
            id: panelFocusScope
            anchors.fill: parent
            focus: true
            Keys.priority: Keys.BeforeItem
            Keys.onEscapePressed: popup.close()

            Flickable {
                anchors.fill: parent; contentWidth: width; contentHeight: contentColumn.implicitHeight
                clip: true; boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick; interactive: contentHeight > height
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                Column {
                    id: contentColumn
                    width: parent.width; spacing: Style.spacing.huge

                    Column {
                        width: parent.width; spacing: Style.spacing.xxs
                        Text { width: parent.width; text: "Workspace presets"; textFormat: Text.PlainText
                            color: Color.popups.text; font.family: Style.font.family
                            font.pixelSize: Style.font.heading; font.weight: Font.Medium }
                        Text { width: parent.width; text: "Save or restore this workspace."
                            textFormat: Text.PlainText; color: root.mutedText
                            font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                    }

                    Column {
                        width: parent.width; spacing: Style.spacing.lg
                        Ui.PanelSectionHeader { text: "SAVE" }
                        Row {
                            width: parent.width; spacing: Style.spacing.controlGap
                            Ui.TextField { id: captureName
                                width: parent.width - saveButton.width - parent.spacing
                                height: Style.spacing.controlHeight; placeholderText: "Preset name"
                                selectByMouse: true; enabled: root.captureReview === null && !client.running
                                onAccepted: saveButton.clicked() }
                            Ui.Button { id: saveButton; width: Style.space(112)
                                height: Style.spacing.controlHeight; text: "Save"; focusable: true
                                enabled: root.captureReview === null && !client.running
                                foreground: Color.accent; bordered: true
                                onClicked: {
                                    if (!captureName.text.trim()) {
                                        root.setStatus("error", "Enter a preset name.")
                                        captureName.forceActiveFocus(); return
                                    }
                                    root.runAction(function() { return client.capture(captureName.text.trim()) },
                                                   "Saving preset…")
                                } }
                        }

                        Ui.BorderSurface {
                            id: captureSurface; visible: root.captureReview !== null; width: parent.width
                            padding: Style.spacing.xl
                            implicitHeight: reviewColumn.implicitHeight + contentTopInset + contentBottomInset
                            height: visible ? implicitHeight : 0
                            color: Util.alpha(Color.accent, 0.08)
                            borderSpec: Border.flat(Util.alpha(Color.accent, 0.58), Style.normalBorderWidth)
                            radius: Style.cornerRadius
                            Column { id: reviewColumn; width: parent.width - captureSurface.contentLeftInset - captureSurface.contentRightInset
                                x: captureSurface.contentLeftInset; y: captureSurface.contentTopInset
                                spacing: Style.spacing.lg
                                Column { width: parent.width; spacing: Style.spacing.xs
                                    Text { width: parent.width; text: "Choose an app"; textFormat: Text.PlainText
                                        color: Color.popups.text; font.family: Style.font.family
                                        font.pixelSize: Style.font.body; font.weight: Font.Medium }
                                    Text { width: parent.width; text: "Choose what should open for each browser window."
                                        textFormat: Text.PlainText; color: root.secondaryText; wrapMode: Text.WordWrap
                                        font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                                }
                                Repeater { model: root.captureReview ? root.captureReview.review : []
                                    delegate: Column { required property var modelData
                                        width: parent.width; spacing: Style.spacing.xs
                                        Text { width: parent.width
                                            text: modelData.title || ("Browser window " + modelData.ordinal)
                                            textFormat: Text.PlainText; color: root.secondaryText; elide: Text.ElideRight
                                            font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                                        Ui.SearchableDropdown { width: parent.width; height: Style.spacing.controlHeight
                                            showLabel: false; placeholderText: "Search installed apps…"
                                            emptyText: "No matching app"; enabled: !client.running
                                            options: root.captureOptions(modelData)
                                            value: root.captureAssignments[modelData.nodeId] || ""
                                            onChanged: function(value) {
                                                let updated = Object.assign({}, root.captureAssignments)
                                                updated[modelData.nodeId] = value; root.captureAssignments = updated
                                                root.captureSelectionRevision++
                                            } }
                                    } }
                                Row { width: parent.width; spacing: Style.spacing.controlGap
                                    Ui.Button { width: (parent.width - parent.spacing) / 2
                                        height: Style.spacing.controlHeight; text: "Cancel"; focusable: true
                                        enabled: !client.running; bordered: true
                                        onClicked: root.cancelCaptureReview() }
                                    Ui.Button { width: (parent.width - parent.spacing) / 2
                                        height: Style.spacing.controlHeight; text: "Save preset"; focusable: true
                                        enabled: root.allCaptureChoicesMade() && !client.running
                                        bordered: true; foreground: Color.accent
                                        onClicked: root.commitCaptureReview() }
                                }
                            }
                        }
                    }

                    Column {
                        width: parent.width; spacing: Style.spacing.lg
                        Ui.PanelSectionHeader { text: "SAVED PRESETS" }
                        Ui.BorderSurface { id: profileSurface; width: parent.width; padding: Style.spacing.md
                            implicitHeight: root.profileRowsHeight + contentTopInset + contentBottomInset
                            height: implicitHeight; color: Util.alpha(Color.popups.text, 0.035)
                            borderSpec: Border.flat(Util.alpha(Color.popups.text, 0.22), Style.normalBorderWidth)
                            radius: Style.cornerRadius
                            ListView { id: profileView; anchors.fill: parent
                                anchors.margins: profileSurface.contentLeftInset; clip: true
                                spacing: Style.spacing.xxs; model: root.profiles
                                boundsBehavior: Flickable.StopAtBounds
                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                                delegate: Ui.Button { required property string modelData
                                    width: profileView.width; height: root.profileRowHeight
                                    text: ""; tooltipText: modelData; focusable: true; enabled: !client.running
                                    selected: modelData === root.selectedProfile; active: selected; hasCursor: selected
                                    foreground: Color.popups.text; accent: Color.accent
                                    onClicked: root.choose(modelData)
                                    Text { anchors.fill: parent; anchors.leftMargin: Style.spacing.controlPaddingX
                                        anchors.rightMargin: Style.spacing.controlPaddingX
                                        text: modelData; textFormat: Text.PlainText
                                        color: selected ? Style.selectedStateColor(Color.popups.text, Color.accent) : Color.popups.text
                                        font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
                                        font.bold: selected; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                                }
                                Text { anchors.centerIn: parent; visible: root.profiles.length === 0
                                    text: "No saved presets yet"; textFormat: Text.PlainText; color: root.mutedText
                                    font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                            }
                        }

                        Ui.BorderSurface { id: detailsSurface; visible: root.selectedProfileData !== null
                            width: parent.width; padding: Style.spacing.xl
                            implicitHeight: detailsColumn.implicitHeight + contentTopInset + contentBottomInset
                            height: visible ? implicitHeight : 0; color: Util.alpha(Color.popups.text, 0.035)
                            borderSpec: Border.flat(Util.alpha(Color.popups.text, 0.18), Style.normalBorderWidth)
                            radius: Style.cornerRadius
                            Column { id: detailsColumn
                                width: parent.width - detailsSurface.contentLeftInset - detailsSurface.contentRightInset
                                x: detailsSurface.contentLeftInset; y: detailsSurface.contentTopInset
                                spacing: Style.spacing.lg
                                Row { width: parent.width; spacing: Style.spacing.controlGap
                                    Text { id: selectedName
                                        width: parent.width - selectedCount.width - parent.spacing
                                        text: root.selectedProfileData ? root.selectedProfileData.name : ""
                                        textFormat: Text.PlainText; color: Color.popups.text; elide: Text.ElideRight
                                        font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
                                        font.weight: Font.Medium
                                        MouseArea { id: selectedNameHover; anchors.fill: parent
                                            acceptedButtons: Qt.NoButton; hoverEnabled: true }
                                        Ui.PanelToolTip { visible: selectedName.truncated && selectedNameHover.containsMouse
                                            text: root.selectedProfileData ? root.selectedProfileData.name : "" }
                                    }
                                    Text { id: selectedCount
                                        readonly property int count: root.selectedProfileData
                                            ? root.selectedProfileData.tiled.nodes.length + root.selectedProfileData.floating.length : 0
                                        text: count + (count === 1 ? " app" : " apps"); textFormat: Text.PlainText
                                        color: root.secondaryText; font.family: Style.font.family
                                        font.pixelSize: Style.font.caption }
                                }
                                ListView { width: parent.width; height: root.detailsListHeight; clip: true
                                    spacing: Style.spacing.xxs; model: root.selectedProfileDetails
                                    boundsBehavior: Flickable.StopAtBounds
                                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                                    delegate: Text { required property var modelData
                                        width: parent.width; height: root.detailRowHeight
                                        text: { let metadata = modelData.metadata; return metadata && metadata.displayName
                                                ? metadata.displayName : "Unavailable app" }
                                        textFormat: Text.PlainText; color: root.secondaryText
                                        font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
                                        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                                }
                            }
                        }

                        Row { width: parent.width; spacing: Style.spacing.controlGap
                            Ui.Button { width: parent.width - deleteButton.width - parent.spacing
                                height: Style.spacing.controlHeight; text: "Restore…"; focusable: true
                                enabled: root.selectedProfile !== "" && !client.running
                                bordered: true; foreground: Color.accent
                                onClicked: { root.planData = null
                                    root.runAction(function() { return client.plan(root.selectedProfile) },
                                                   "Preparing preview…") } }
                            Ui.Button { id: deleteButton; width: Style.space(92)
                                height: Style.spacing.controlHeight; text: "Delete"; focusable: true
                                enabled: root.selectedProfile !== "" && !client.running
                                foreground: Color.urgent; bordered: true
                                onClicked: root.confirmDelete = true }
                        }

                        Ui.BorderSurface { id: deleteSurface; visible: root.confirmDelete
                            width: parent.width; padding: Style.spacing.xl
                            implicitHeight: Math.max(deleteQuestion.implicitHeight, deleteCancel.implicitHeight,
                                                     deleteConfirm.implicitHeight) + contentTopInset + contentBottomInset
                            height: visible ? implicitHeight : 0; color: Util.alpha(Color.urgent, 0.12)
                            borderSpec: Border.flat(Util.alpha(Color.urgent, 0.62), Style.normalBorderWidth)
                            radius: Style.cornerRadius
                            Row { width: parent.width - deleteSurface.contentLeftInset - deleteSurface.contentRightInset
                                x: deleteSurface.contentLeftInset; anchors.verticalCenter: parent.verticalCenter
                                spacing: Style.spacing.controlGap
                                Text { id: deleteQuestion
                                    width: parent.width - deleteCancel.width - deleteConfirm.width - parent.spacing * 2
                                    text: "Delete “" + root.selectedProfile + "”?"; textFormat: Text.PlainText
                                    color: Color.popups.text; elide: Text.ElideRight
                                    font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
                                    anchors.verticalCenter: parent.verticalCenter }
                                Ui.Button { id: deleteCancel; width: Style.space(76)
                                    height: Style.spacing.controlHeight; text: "Cancel"; focusable: true
                                    enabled: !client.running; bordered: true; onClicked: root.confirmDelete = false }
                                Ui.Button { id: deleteConfirm; width: Style.space(76)
                                    height: Style.spacing.controlHeight; text: "Delete"; focusable: true
                                    enabled: !client.running; foreground: Color.urgent; bordered: true
                                    onClicked: { root.confirmDelete = false
                                        root.runAction(function() { return client.remove(root.selectedProfile) },
                                                       "Deleting preset…") } }
                            }
                        }

                        Plugin.RestorePreview { width: parent.width; plan: root.planData; busy: client.running
                            onRestoreRequested: root.runAction(
                                function() { return client.restore(root.planData.planId) }, "Restoring…") }
                    }

                    Text { width: parent.width; visible: text.length > 0; text: root.statusText
                        textFormat: Text.PlainText; color: root.statusColor
                        horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                        font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
                        maximumLineCount: 2; elide: Text.ElideRight }
                }
            }
        }
    }
}
