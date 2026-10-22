// 状态卡片：上面一行小标题，下面一个大数字。
// 圆角按「外圆角 = 内圆角 + 内边距」来，卡片 14、内部内容间距 14。
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import BrushUI 1.0

Rectangle {
    id: root

    property string title: ""
    property string value: "—"
    property string tip: ""

    radius: Theme.rCard
    color: Theme.col("surface")
    border.width: 1
    border.color: Theme.col("border")

    implicitHeight: col.implicitHeight + Theme.spCard * 2
    implicitWidth: 168

    ColumnLayout {
        id: col
        anchors.fill: parent
        anchors.margins: Theme.spCard
        spacing: 4

        Label {
            text: root.title
            font.family: Theme.fontUI
            font.pixelSize: Theme.fsSmall
            color: Theme.col("muted")
            Layout.fillWidth: true
        }

        Label {
            text: root.value
            font.family: Theme.fontUI
            font.pixelSize: Theme.fsBig
            font.bold: true
            color: Theme.col("fg")
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
    }

    ToolTip.visible: (root.tip || "").length > 0 && ma.containsMouse
    ToolTip.text: root.tip || ""
    ToolTip.delay: 500

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        propagateComposedEvents: true
    }
}