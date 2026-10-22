// 运行日志：一行一条，正文自动换行，永不横向滚动。
// 排版：时间（灰、等宽对齐）+ 级别小标签（带色）+ 正文（黑体、加大、自动折行）。
// 顶部只保留“运行日志”标题。
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import BrushUI 1.0

Item {
    id: root

    // 由控制层灌进来的批量日志
    function appendBatch(batch) {
        if (!batch || batch.length === 0) return;
        for (var i = 0; i < batch.length; i++) {
            var it = batch[i];
            var lv = (it[1] || "INFO").toUpperCase();
            logModel.append({ "t": it[0] || "", "lv": lv, "txt": it[2] || "" });
        }
        if (logModel.count > 2000) {
            var extra = logModel.count - 2000;
            logModel.remove(0, extra);
        }
    }

    function clearAll() {
        logModel.clear();
    }

    // 导出成纯文本（复制 / 保存用）
    function asText() {
        var out = [];
        for (var i = 0; i < logModel.count; i++) {
            var r = logModel.get(i);
            out.push("[" + r.t + "] [" + r.lv + "] " + r.txt);
        }
        return out.join("\n");
    }

    property bool autoScroll: true
    property var levelFilter: ["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"]

    function toggleLevel(lv) {
        var arr = levelFilter.slice();
        var idx = arr.indexOf(lv);
        if (idx >= 0) arr.splice(idx, 1);
        else arr.push(lv);
        levelFilter = arr;
    }

    ListModel {
        id: logModel
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        // ---------- 顶部：标题 ----------
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Label {
                text: "运行日志"
                font.family: Theme.fontUI
                font.pixelSize: Theme.fsBase
                font.bold: true
                color: Theme.col("fg")
            }

            Item { Layout.fillWidth: true }

        }

        // ---------- 日志列表 ----------
        Rectangle {
            id: logBox
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.rCard
            color: Theme.col("logBg")
            border.width: 1
            border.color: Theme.col("border")
            clip: true

            ListView {
                id: view
                anchors.fill: parent
                anchors.margins: 8
                model: logModel
                spacing: 2
                clip: true
                // 高频刷新的日志一律不加动画，不然看着卡

                delegate: RowLayout {
                    width: view.width
                    spacing: 8
                    // 被筛掉的级别直接不占高度
                    visible: root.levelFilter.indexOf(model.lv) >= 0
                    height: visible ? Math.max(timeTxt.implicitHeight, bodyTxt.contentHeight) + 2 : 0

                    Text {
                        id: timeTxt
                        text: model.t
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsLog - 1
                        color: Theme.col("logTimeFg")
                        Layout.preferredWidth: 64
                        verticalAlignment: Text.AlignTop
                        visible: model.t.length > 0
                    }

                    Rectangle {
                        radius: Theme.rTag
                        color: Theme.levelColor(model.lv)
                        Layout.preferredWidth: model.lv.length > 2 ? 40 : 34
                        Layout.preferredHeight: 17
                        Layout.alignment: Qt.AlignTop
                        Text {
                            anchors.centerIn: parent
                            text: Theme.levelLabel(model.lv)
                            font.family: Theme.fontUI
                            font.pixelSize: 11
                            color: "#FFFFFF"
                        }
                    }

                    TextEdit {
                        id: bodyTxt
                        text: model.txt
                        font.family: Theme.fontLog
                        font.pixelSize: Theme.fsLog
                        color: Theme.levelColor(model.lv)
                        wrapMode: TextEdit.Wrap        // 整行自动折行
                        readOnly: true                  // 只读，不能编辑
                        selectByMouse: true             // 可以用鼠标拖选
                        selectedTextColor: Theme.col("primaryText")
                        selectionColor: Theme.col("primary")
                        Layout.fillWidth: true
                        Layout.preferredHeight: contentHeight
                        textFormat: TextEdit.PlainText
                        // TextEdit 默认没有垂直对齐，这里让它贴着顶部
                        topPadding: 0
                        bottomPadding: 0
                        leftPadding: 0
                        rightPadding: 0
                    }
                }

                // 自动滚到最新一条
                onCountChanged: {
                    if (root.autoScroll) Qt.callLater(view.positionViewAtEnd);
                }

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
            }
        }
    }

    // 复制请求：交给外层去真正写剪贴板
    signal copyRequested(string text)
    signal clearRequested()
    property bool copiedFlash: false
    Timer {
        id: flashTimer
        interval: 1200
        repeat: false
        onTriggered: root.copiedFlash = false
    }
}