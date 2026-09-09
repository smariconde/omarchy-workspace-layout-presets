import QtQuick

Item {
    id: root
    property var plan: null
    signal restoreRequested()
    visible: plan !== null
    Rectangle {
        anchors.fill: parent; radius: 5; color: "#182026"; border.color: "#48515c"
        Column {
            anchors.fill: parent; anchors.margins: 8; spacing: 3
            Text { text: root.plan ? "Vista previa · " + root.plan.layoutMode : ""; color: "white"; font.bold: true }
            Text { text: root.plan ? ("Lanzar: " + root.plan.summary.launch + " · Omitir: " + root.plan.summary.skip + " · Tiled: " + root.plan.summary.tiled + " · Floating: " + root.plan.summary.floating) : ""; color: "#b8c0cc"; font.pixelSize: 11 }
            Text { width: parent.width; text: root.plan ? ("Workspace " + root.plan.target.workspace.name + " · " + root.plan.target.monitor.connector) : ""; color: "#b8c0cc"; font.pixelSize: 11; elide: Text.ElideRight }
            Text { width: parent.width; text: root.plan ? ((root.plan.warnings && root.plan.warnings.length) ? root.plan.warnings[0].message : "Listo para restaurar.") : ""; color: "#f3c969"; font.pixelSize: 11; elide: Text.ElideRight }
            Rectangle { width: 112; height: 27; radius: 4; color: "#8bd5ca"; visible: root.plan !== null
                Text { anchors.centerIn: parent; text: "Restaurar aquí"; color: "#12201e"; font.bold: true; font.pixelSize: 12 }
                MouseArea { anchors.fill: parent; onClicked: root.restoreRequested() } }
        }
    }
}
