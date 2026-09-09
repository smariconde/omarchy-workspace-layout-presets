import QtQuick
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
    property color panelColor: "#20242b"
    property color cardColor: "#2c323b"
    property color accentColor: "#8bd5ca"
    implicitWidth: 390
    implicitHeight: 740
    Plugin.LayoutctlClient { id: client }

    function messageFrom(response, fallback) {
        if (response && response.error && response.error.message) return response.error.message
        if (response && response.blocked && response.blocked.length) return response.blocked[0].message
        return fallback
    }
    function refresh() { statusText = "Cargando perfiles..."; client.listProfiles() }
    function choose(profileId) {
        selectedProfile = profileId; selectedProfileData = null; planData = null; confirmRestore = false
        confirmDelete = false; client.showProfile(profileId)
    }
    function runAction(action, text) {
        if (!action()) statusText = "El backend está ocupado."; else statusText = text
    }

    Connections {
        target: client
        function onCommandFinished(operation, exitCode, response, stderrText) {
            if (operation === "profile-list") {
                if (response && response.status === "ok") {
                    root.profiles = response.data.profiles || []
                    root.statusText = root.profiles.length ? "Seleccioná un perfil." : "Todavía no hay perfiles guardados."
                } else root.statusText = root.messageFrom(response, stderrText || "No se pudo listar perfiles.")
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
                if (operation === "capture" || operation === "profile-rename" || operation === "profile-duplicate" || operation === "profile-delete" || operation === "profile-import") {
                    root.statusText = "Operación completada."; root.refresh()
                }
                if (operation === "restore") {
                    root.statusText = (response.data.failures && response.data.failures.length) ? "Restauración parcial: revisá el resultado." : "Restauración completada."
                    root.confirmRestore = false; root.planData = null
                }
            } else {
                root.statusText = root.messageFrom(response, stderrText || "La operación fue bloqueada.")
                root.confirmRestore = false; root.confirmDelete = false
            }
        }
    }

    Ui.KeyboardPanel {
        id: popup
        anchorItem: root.anchorItem
        owner: root.barIdentity
        bar: root.bar
        open: root.opened
        centerOnBar: true
        contentWidth: root.implicitWidth
        contentHeight: root.implicitHeight

        Rectangle {
            anchors.fill: parent; color: root.panelColor; radius: 10
            border.color: "#48515c"; border.width: 1
        Column {
            anchors.fill: parent; anchors.margins: 14; spacing: 8
            Row {
                width: parent.width; spacing: 10
                Text { text: "Workspace layouts"; color: "white"; font.pixelSize: 18; font.bold: true }
                Item { width: parent.width - 190; height: 1 }
                Text { text: "×"; color: "#b8c0cc"; font.pixelSize: 22
                    MouseArea { anchors.fill: parent; onClicked: root.open = false } }
            }
            Text { width: parent.width; text: "Guardá y restaurá sólo el workspace activo y vacío."; color: "#b8c0cc"; wrapMode: Text.WordWrap; font.pixelSize: 12 }
            Rectangle { width: parent.width; height: 1; color: "#48515c" }
            Row {
                width: parent.width; spacing: 6
                Ui.TextField {
                    id: captureName; width: parent.width - 92; height: 32; color: "white"; padding: 8; clip: true
                    placeholderText: "Nombre del perfil"; selectByMouse: true
                    Rectangle { anchors.fill: parent; z: -1; color: "#15181d"; radius: 5; border.color: "#48515c" }
                }
                Rectangle {
                    width: 86; height: 32; radius: 5; color: root.accentColor
                    Text { anchors.centerIn: parent; text: "Guardar"; color: "#12201e"; font.bold: true }
                    MouseArea { anchors.fill: parent; onClicked: {
                        if (!captureName.text.trim()) { root.statusText = "Escribí un nombre."; return }
                        root.runAction(function() { return client.capture(captureName.text.trim()) }, "Guardando workspace...")
                        captureName.text = ""
                    }}
                }
            }
            Text { text: "Perfiles"; color: "white"; font.bold: true; font.pixelSize: 14 }
            ListView {
                id: profileView; width: parent.width; height: 108; clip: true; model: root.profiles
                delegate: Rectangle {
                    width: profileView.width; height: 32; radius: 4
                    color: modelData === root.selectedProfile ? "#43515d" : "transparent"
                    Text { anchors.verticalCenter: parent.verticalCenter; x: 8; text: modelData; color: "white" }
                    MouseArea { anchors.fill: parent; onClicked: root.choose(modelData) }
                }
            }
            Row {
                width: parent.width; spacing: 5
                Repeater {
                    model: ["Inspeccionar", "Planificar", "Borrar"]
                    delegate: Rectangle {
                        width: (parent.width - 10) / 3; height: 30; radius: 5
                        color: index === 2 ? "#603d46" : root.cardColor
                        Text { anchors.centerIn: parent; text: modelData; color: "white"; font.pixelSize: 12 }
                        MouseArea { anchors.fill: parent; onClicked: {
                            if (!root.selectedProfile) { root.statusText = "Elegí un perfil primero."; return }
                            if (index === 0) client.showProfile(root.selectedProfile)
                            else if (index === 1) { root.planData = null; client.plan(root.selectedProfile); root.statusText = "Preparando vista previa..." }
                            else root.confirmDelete = true
                        }}
                    }
                }
            }
            Rectangle {
                visible: root.confirmDelete; width: parent.width; height: 34; radius: 5; color: "#603d46"
                Text { x: 8; anchors.verticalCenter: parent.verticalCenter; text: "¿Eliminar " + root.selectedProfile + "?"; color: "white"; font.pixelSize: 12 }
                Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: "Confirmar"; color: "#ffb4c3"; font.bold: true
                    MouseArea { anchors.fill: parent; onClicked: { root.confirmDelete = false; client.remove(root.selectedProfile) } } }
            }
            Plugin.RestorePreview {
                width: parent.width; height: 122; plan: root.planData
                onRestoreRequested: root.confirmRestore = true
            }
            Rectangle {
                visible: root.selectedProfileData !== null
                width: parent.width; height: 46; radius: 5; color: "#182026"
                Text {
                    anchors.fill: parent; anchors.margins: 7; color: "#b8c0cc"; font.pixelSize: 11
                    text: root.selectedProfileData
                        ? (root.selectedProfileData.name + " · " + root.selectedProfileData.layoutConfidence
                           + " · tiled " + root.selectedProfileData.tiled.nodes.length
                           + " · floating " + root.selectedProfileData.floating.length)
                        : ""
                    elide: Text.ElideRight
                }
            }
            Rectangle {
                visible: root.confirmRestore; width: parent.width; height: 34; radius: 5; color: "#735c2f"
                Text { x: 8; anchors.verticalCenter: parent.verticalCenter; text: "Restaurar en workspace vacío"; color: "white"; font.pixelSize: 12 }
                Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: "Confirmar"; color: "#ffe2a3"; font.bold: true
                    MouseArea { anchors.fill: parent; onClicked: { root.confirmRestore = false; client.restore(root.planData.planId) } } }
            }
            Row {
                width: parent.width; spacing: 6
                Ui.TextField { id: renameInput; width: parent.width - 96; height: 30; color: "white"; padding: 7; placeholderText: "Nuevo nombre"
                    Rectangle { anchors.fill: parent; z: -1; color: "#15181d"; radius: 5; border.color: "#48515c" } }
                Rectangle { width: 90; height: 30; radius: 5; color: root.cardColor
                    Text { anchors.centerIn: parent; text: "Renombrar"; color: "white"; font.pixelSize: 12 }
                    MouseArea { anchors.fill: parent; onClicked: {
                        if (root.selectedProfile && renameInput.text.trim()) client.rename(root.selectedProfile, renameInput.text.trim()); else root.statusText = "Elegí perfil y nombre."
                    }} }
            }
            Row {
                width: parent.width; spacing: 6
                Ui.TextField { id: exportPath; width: parent.width - 96; height: 30; color: "white"; padding: 7; placeholderText: "Ruta para exportar/importar"
                    Rectangle { anchors.fill: parent; z: -1; color: "#15181d"; radius: 5; border.color: "#48515c" } }
                Rectangle { width: 90; height: 30; radius: 5; color: root.cardColor
                    Text { anchors.centerIn: parent; text: "Exportar"; color: "white"; font.pixelSize: 12 }
                    MouseArea { anchors.fill: parent; onClicked: {
                        if (root.selectedProfile && exportPath.text.trim()) client.exportProfile(root.selectedProfile, exportPath.text.trim()); else root.statusText = "Elegí perfil y ruta."
                    }} }
            }
            Row {
                width: parent.width; spacing: 6
                Item { width: parent.width - 96; height: 30 }
                Rectangle { width: 90; height: 30; radius: 5; color: root.cardColor
                    Text { anchors.centerIn: parent; text: "Importar"; color: "white"; font.pixelSize: 12 }
                    MouseArea { anchors.fill: parent; onClicked: {
                        if (exportPath.text.trim()) client.importProfile(exportPath.text.trim()); else root.statusText = "Escribí la ruta del JSON."
                    }} }
            }
            Row {
                width: parent.width; spacing: 6
                Ui.TextField { id: copyInput; width: parent.width - 96; height: 30; color: "white"; padding: 7; placeholderText: "ID de la copia"
                    Rectangle { anchors.fill: parent; z: -1; color: "#15181d"; radius: 5; border.color: "#48515c" } }
                Rectangle { width: 90; height: 30; radius: 5; color: root.cardColor
                    Text { anchors.centerIn: parent; text: "Duplicar"; color: "white"; font.pixelSize: 12 }
                    MouseArea { anchors.fill: parent; onClicked: {
                        if (root.selectedProfile && copyInput.text.trim()) client.duplicate(root.selectedProfile, copyInput.text.trim()); else root.statusText = "Elegí perfil y un ID."
                    }} }
            }
            Text { width: parent.width; text: root.statusText; color: root.accentColor; wrapMode: Text.WordWrap; font.pixelSize: 12; maximumLineCount: 2; elide: Text.ElideRight }
            Item { width: 1; height: 1; Component.onCompleted: root.refresh() }
        }
    }
}
