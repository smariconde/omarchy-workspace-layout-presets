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
    property var planData: null
    property bool confirmRestore: false
    property bool confirmDelete: false
    property string statusText: ""

    readonly property int panelWidth: Style.space(410)
    readonly property int panelHeight: Style.space(500
        + (planData ? 132 : 0)
        + (selectedProfileData ? 42 : 0)
        + (confirmDelete ? 38 : 0)
        + (confirmRestore ? 38 : 0))
    implicitWidth: panelWidth
    implicitHeight: panelHeight

    Plugin.LayoutctlClient { id: client }

    function messageFrom(response, fallback) {
        if (response && response.error && response.error.message) return response.error.message
        if (response && response.blocked && response.blocked.length) return response.blocked[0].message
        return fallback
    }
    function refresh() {
        statusText = "Cargando perfiles…"
        client.listProfiles()
    }
    function choose(profileId) {
        selectedProfile = profileId
        selectedProfileData = null
        planData = null
        confirmRestore = false
        confirmDelete = false
        client.showProfile(profileId)
    }
    function runAction(action, text) {
        if (!action()) statusText = "El backend está ocupado."
        else statusText = text
    }

    Connections {
        target: client
        function onCommandFinished(operation, exitCode, response, stderrText) {
            if (operation === "profile-list") {
                if (response && response.status === "ok") {
                    root.profiles = response.data.profiles || []
                    root.statusText = root.profiles.length
                        ? "Seleccioná un preset para ver sus acciones."
                        : "Todavía no hay presets guardados."
                } else root.statusText = root.messageFrom(response, stderrText || "No se pudo listar presets.")
                return
            }
            if (response && response.status === "ok") {
                if (operation === "profile-show") root.selectedProfileData = response.data.profile
                if (operation === "plan") {
                    var preview = response.data
                    preview.warnings = response.warnings || []
                    root.planData = preview
                    root.confirmRestore = false
                }
                if (operation === "capture" || operation === "profile-rename"
                        || operation === "profile-duplicate" || operation === "profile-delete"
                        || operation === "profile-import") {
                    root.statusText = "Operación completada."
                    root.refresh()
                }
                if (operation === "restore") {
                    root.statusText = response.data.failures && response.data.failures.length
                        ? "Restauración parcial: revisá el resultado."
                        : "Restauración completada."
                    root.confirmRestore = false
                    root.planData = null
                }
            } else {
                root.statusText = root.messageFrom(response, stderrText || "La operación fue bloqueada.")
                root.confirmRestore = false
                root.confirmDelete = false
            }
        }
    }

    Ui.KeyboardPanel {
        id: popup
        anchorItem: root.anchorItem
        owner: root.barIdentity
        bar: root.bar
        open: root.opened
        centerOnBar: false
        contentWidth: root.panelWidth
        contentHeight: root.panelHeight

        Column {
            anchors.fill: parent
            spacing: Style.spacing.panelGap

            Column {
                width: parent.width
                spacing: Style.spacing.xxs
                Text {
                    text: "Workspace layouts"
                    color: Color.popups.text
                    font.family: Style.font.family
                    font.pixelSize: Style.font.heading
                    font.weight: Font.Medium
                }
                Text {
                    text: "Presets para el workspace activo"
                    color: Color.popups.text
                    opacity: 0.58
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                }
            }

                Text {
                    width: parent.width
                    text: "Guardá y restaurá sólo el workspace activo y vacío."
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

                Ui.PanelSectionHeader { text: "Guardar preset" }
                Row {
                    width: parent.width
                    spacing: Style.spacing.controlGap
                    Ui.TextField {
                        id: captureName
                        width: parent.width - saveButton.width - parent.spacing
                        height: Style.spacing.controlHeight
                        placeholderText: "Nombre del preset"
                        selectByMouse: true
                        onAccepted: saveButton.clicked()
                    }
                    Ui.Button {
                        id: saveButton
                        width: Style.space(86)
                        height: Style.spacing.controlHeight
                        text: "Guardar"
                        foreground: Color.accent
                        bordered: true
                        onClicked: {
                            if (!captureName.text.trim()) {
                                root.statusText = "Escribí un nombre."
                                captureName.forceActiveFocus()
                                return
                            }
                            root.runAction(function() { return client.capture(captureName.text.trim()) }, "Guardando preset…")
                            captureName.text = ""
                        }
                    }
                }

                Ui.PanelSectionHeader { text: "Presets" }
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
                            text: "No hay presets guardados"
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
                        width: (parent.width - Style.spacing.xs * 2) / 3
                        height: Style.spacing.controlHeight
                        text: "Inspeccionar"
                        enabled: root.selectedProfile !== ""
                        bordered: true
                        onClicked: client.showProfile(root.selectedProfile)
                    }
                    Ui.Button {
                        width: (parent.width - Style.spacing.xs * 2) / 3
                        height: Style.spacing.controlHeight
                        text: "Planificar"
                        enabled: root.selectedProfile !== ""
                        bordered: true
                        foreground: Color.accent
                        onClicked: {
                            root.planData = null
                            client.plan(root.selectedProfile)
                            root.statusText = "Preparando vista previa…"
                        }
                    }
                    Ui.Button {
                        width: (parent.width - Style.spacing.xs * 2) / 3
                        height: Style.spacing.controlHeight
                        text: "Borrar"
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
                            text: "¿Eliminar “" + root.selectedProfile + "”?"
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
                            text: "Confirmar"
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
                    onRestoreRequested: root.confirmRestore = true
                }

                Ui.BorderSurface {
                    visible: root.selectedProfileData !== null
                    width: parent.width
                    height: root.selectedProfileData ? Style.space(42) : 0
                    color: Util.alpha(Color.popups.text, 0.035)
                    borderSpec: Border.flat(Util.alpha(Color.popups.text, 0.18), Style.normalBorderWidth)
                    radius: Style.cornerRadius
                    Text {
                        anchors.fill: parent
                        anchors.margins: Style.spacing.sm
                        color: Color.popups.text
                        opacity: 0.66
                        font.family: Style.font.family
                        font.pixelSize: Style.font.caption
                        elide: Text.ElideRight
                        text: root.selectedProfileData
                            ? (root.selectedProfileData.name + " · " + root.selectedProfileData.layoutConfidence
                               + " · tiled " + root.selectedProfileData.tiled.nodes.length
                               + " · floating " + root.selectedProfileData.floating.length)
                            : ""
                    }
                }

                Ui.BorderSurface {
                    visible: root.confirmRestore
                    width: parent.width
                    height: root.confirmRestore ? Style.space(38) : 0
                    color: Util.alpha(Color.accent, 0.12)
                    borderSpec: Border.flat(Util.alpha(Color.accent, 0.62), Style.normalBorderWidth)
                    radius: Style.cornerRadius
                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: Style.spacing.sm
                        anchors.rightMargin: Style.spacing.xs
                        spacing: Style.spacing.sm
                        Text {
                            width: parent.width - restoreConfirmButton.width - parent.spacing
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Restaurar en workspace vacío"
                            color: Color.popups.text
                            elide: Text.ElideRight
                            font.family: Style.font.family
                            font.pixelSize: Style.font.bodySmall
                        }
                        Ui.Button {
                            id: restoreConfirmButton
                            width: Style.space(82)
                            height: Style.spacing.controlHeight
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Confirmar"
                            foreground: Color.accent
                            onClicked: {
                                root.confirmRestore = false
                                client.restore(root.planData.planId)
                            }
                        }
                    }
                }

                Row {
                    width: parent.width
                    spacing: Style.spacing.controlGap
                    Ui.TextField {
                        id: renameInput
                        width: parent.width - renameButton.width - parent.spacing
                        height: Style.spacing.controlHeight
                        placeholderText: "Nuevo nombre"
                    }
                    Ui.Button {
                        id: renameButton
                        width: Style.space(92)
                        height: Style.spacing.controlHeight
                        text: "Renombrar"
                        enabled: root.selectedProfile !== ""
                        bordered: true
                        onClicked: {
                            if (renameInput.text.trim()) client.rename(root.selectedProfile, renameInput.text.trim())
                            else root.statusText = "Escribí un nombre nuevo."
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: root.statusText
                    color: root.statusText.indexOf("bloque") >= 0 || root.statusText.indexOf("No se pudo") >= 0
                        ? Color.urgent : Color.popups.text
                    opacity: 0.75
                    wrapMode: Text.WordWrap
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                Item {
                    width: 1
                    height: 1
                    Component.onCompleted: root.refresh()
                }
            }
    }
}
