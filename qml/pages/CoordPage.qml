// 坐标校准页：改坐标 + 管理多套方案（存多套、随时切换）。
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import BrushUI 1.0
import "../components"

Item {
    id: root

    property var profiles: []
    property string currentName: ""

    function refreshProfiles() {
        profiles = backend.profileList();
        currentName = backend.currentProfile();
        var names = [];
        for (var i = 0; i < profiles.length; i++) names.push(profiles[i].name);
        var idx = names.indexOf(currentName);
        profileCombo.model = names;
        profileCombo.currentIndex = (idx >= 0) ? idx : -1;
    }

    Component.onCompleted: refreshProfiles()

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        // ---------- 顶部：标题 + 操作 ----------
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Label {
                text: "坐标校准"
                font.family: Theme.fontUI
                font.pixelSize: Theme.fsBase
                font.bold: true
                color: Theme.col("fg")
            }
            Item { Layout.fillWidth: true }
            ActionButton {
                text: "重新检测"
                iconName: "refresh"
                variant: "neutral"
                onClicked: backend.reloadCoordinates()
            }
            ActionButton {
                text: "保存到配置"
                iconName: "save"
                variant: "primary"
                onClicked: {
                    var err = backend.saveCoordinates();
                    backend.toast(err ? err : "坐标已保存到 config.json");
                }
            }
        }

        // ---------- 方案管理行 ----------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            radius: Theme.rCard
            color: Theme.col("surface")
            border.width: 1
            border.color: Theme.col("border")

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                Label {
                    text: "坐标方案"
                    font.family: Theme.fontUI
                    font.pixelSize: Theme.fsSmall
                    color: Theme.col("muted")
                }

                ComboBox {
                    id: profileCombo
                    Layout.preferredWidth: 200
                    Layout.preferredHeight: 32
                    font.family: Theme.fontUI
                    font.pixelSize: Theme.fsSmall
                    model: []
                    onActivated: root.currentName = currentText
                }

                ActionButton {
                    text: "切换"
                    iconName: "play"
                    variant: "neutral"
                    enabled: profileCombo.currentIndex >= 0
                    onClicked: {
                        var err = backend.switchProfile(profileCombo.currentText);
                        backend.toast(err ? err : "已切换到方案：" + profileCombo.currentText);
                        root.refreshProfiles();
                    }
                }

                ActionButton {
                    text: "另存为"
                    iconName: "save"
                    variant: "neutral"
                    onClicked: saveDialog.open()
                }

                ActionButton {
                    text: "删除"
                    iconName: "stop"
                    variant: "danger"
                    enabled: profileCombo.currentIndex >= 0
                    onClicked: {
                        var err = backend.deleteProfile(profileCombo.currentText);
                        backend.toast(err ? err : "已删除方案：" + profileCombo.currentText);
                        root.refreshProfiles();
                    }
                }

                Item { Layout.fillWidth: true }

                Label {
                    text: root.currentName ? ("当前：" + root.currentName) : "当前：未设置"
                    font.family: Theme.fontUI
                    font.pixelSize: Theme.fsSmall
                    color: Theme.col("muted")
                }
            }
        }

        // ---------- 坐标列表 ----------
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
                model: backend ? backend.coordModel : null
                spacing: 6
                clip: true
                delegate: RowLayout {
                    width: list.width
                    spacing: 8
                    Label {
                        text: (model.name || "")
                        font.family: Theme.fontUI
                        font.pixelSize: Theme.fsBase
                        color: Theme.col("fg")
                        Layout.preferredWidth: 190
                        elide: Text.ElideRight
                    }
                    TextField {
                        text: (model.value || "")
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsBase
                        Layout.fillWidth: true
                        onEditingFinished: {
                            if (backend) backend.setCoordValue(index, text);
                        }
                    }
                }
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
        }
    }

    // 另存为弹窗
    Dialog {
        id: saveDialog
        title: "保存为新方案"
        modal: true
        anchors.centerIn: parent
        width: 380
        standardButtons: Dialog.Ok | Dialog.Cancel

        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            Label {
                text: "给这套坐标起个名字："
                font.family: Theme.fontUI
                font.pixelSize: Theme.fsBase
                color: Theme.col("fg")
            }
            TextField {
                id: nameField
                Layout.fillWidth: true
                placeholderText: "例如：作者的方案"
                font.family: Theme.fontUI
                font.pixelSize: Theme.fsBase
            }
        }

        onAccepted: {
            var err = backend.saveProfileAs(nameField.text);
            backend.toast(err ? err : "已保存方案：" + nameField.text);
            root.refreshProfiles();
            nameField.text = "";
        }
    }
}