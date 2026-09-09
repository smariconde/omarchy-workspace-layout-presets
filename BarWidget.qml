import QtQuick

Item {
    id: root
    implicitWidth: 30
    implicitHeight: 30
    Rectangle {
        anchors.fill: parent; radius: 5; color: mouse.containsMouse ? "#43515d" : "transparent"
        Text { anchors.centerIn: parent; text: "▦"; color: "white"; font.pixelSize: 18 }
        MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; onClicked: panel.open = !panel.open }
    }
    Panel { id: panel; x: -implicitWidth + root.width; y: root.height + 6; z: 100 }
}
