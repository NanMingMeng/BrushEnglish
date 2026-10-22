// 题库页：查单词、看释义、看哪些已经确认过。
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import BrushUI 1.0
import "../components"

Item {
    id: root

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            TextField {
                id: searchBox
                Layout.fillWidth: true
                placeholderText: "输入单词或者意思，回车筛选"
                font.family: Theme.fontUI
                font.pixelSize: Theme.fsBase
                onAccepted: backend.filterBank(text)
            }

            ActionButton {
                text: "刷新"
                iconName: "refresh"
                variant: "neutral"
                onClicked: backend.reloadBank()
            }

            ActionButton {
                text: "打开题库文件夹"
                iconName: "folder"
                variant: "neutral"
                onClicked: backend.openBankFolder()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.rCard
            color: Theme.col("surface")
            border.width: 1
            border.color: Theme.col("border")
            clip: true

            ListView {
                id: list
                anchors.fill: parent
                anchors.margins: 8
                model: backend ? backend.bankModel : null
                spacing: 2
                clip: true
                delegate: RowLayout {
                    width: list.width
                    spacing: 10

                    Label {
                        text: (model.no !== undefined) ? String(model.no) : ""
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsBase
                        color: Theme.col("muted")
                        Layout.preferredWidth: 52
                    }
                    Label {
                        text: (model.word || "")
                        font.family: Theme.fontUI
                        font.pixelSize: Theme.fsBase
                        font.bold: true
                        color: Theme.col("fg")
                        Layout.preferredWidth: 150
                        elide: Text.ElideRight
                    }
                    Label {
                        text: (model.meaning || "")
                        font.family: Theme.fontUI
                        font.pixelSize: Theme.fsBase
                        color: Theme.col("fg")
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }
                    Label {
                        text: model.confirmed ? "已确认" : "未确认"
                        font.family: Theme.fontUI
                        font.pixelSize: Theme.fsSmall
                        color: model.confirmed ? Theme.col("ok") : Theme.col("muted")
                        Layout.preferredWidth: 56
                    }
                }

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
        }
    }
}