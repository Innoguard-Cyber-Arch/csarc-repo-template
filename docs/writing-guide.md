# 中文寫作指引

本指引適用於模板擁有的繁體中文（台灣）文字：文件、表單、範本與 agent 指示。新寫的文字照本指引寫；修改既有文字時，改到的句子也要符合。英文文字與腳本訊息依 [`writing-guide.en.md`](writing-guide.en.md)。

規則重點整理自 speak-human-tw v1.4.0（commit `72279f8`），完整規則見 <https://github.com/Raymondhou0917/speak-human-tw>。標點以教育部《重訂標點符號手冊》為準。你可以自行安裝該 skill 校稿；模板不安裝、也不依賴它。

## 原則

先保事實，再刪套話。一句話刪掉後讀者沒有少知道任何事，就刪；寫不出具體內容的句子，多半該刪，不該換個說法。

## 保護清單

改寫時下列內容一字不動：

- 數字、版本、日期與門檻值。
- 指令、路徑、設定鍵、程式碼、專有名詞與產品名。
- 連結本體與錨點文字。
- 引號內的原話。
- 授權、安全與發布規則等承諾條款：只能調語氣，不能調意思。

## 刪除 AI 痕跡

- C1. 刪對話殘留與客套：「希望對你有幫助」「以下是」「好問題」。
- C2. 刪預告式導言：不寫「本節將說明」，直接說明。
- C3. 刪公式化開場與空洞結論：「隨著技術快速發展」「總的來說」「未來充滿可能」。結尾停在最後一個具體句子即可。
- C4. 「不是 A，而是 B」與「不僅⋯⋯更⋯⋯」一篇最多各用一次，其餘改直述。
- C5. 誇大詞（標誌著、奠定基礎、體現了、賦能、閉環）改成具體事實；寫不出就刪，不換同類詞。
- C6. 沒有出處的權威（「研究顯示」「業界普遍認為」）刪除或補上出處。
- C7. 不寫「各有優缺點」「視情況而定」；寫出明確判斷與條件。
- C8. 不硬湊「首先、其次、最後」三點；結構跟著內容走。
- C9. 同一概念全文只用一個詞，不為了變化而換詞。
- C10. 粗體一段最多兩三個詞；破折號少用；表格只用於真正的多欄比較；文件不用 emoji。

## 台灣用語

| 不用 | 改用 |
| --- | --- |
| 視頻、信息、質量、網絡 | 影片、資訊、品質、網路 |
| 軟件、數據庫、服務器 | 軟體、資料庫、伺服器 |
| 默認、支持（功能）、兼容、卸載 | 預設、支援、相容、移除 |
| 反饋、落地、打法 | 回饋、實作、做法 |
| 項目、代碼、配置、創建、調用、運行 | 專案、程式碼、設定、建立、呼叫、執行 |

最後一列是本模板補充的技術用語。「優化」只在後面接得出改了什麼、變化多少時使用。被討論的詞（提及而非使用）照原文。

## 標點

- 中文句一律用全形標點：，。、；：？！「」『』（）《》〈〉。
- 引號先用「」，引號內再用『』；不用 “ ” 或半形 "。
- 刪節號用「⋯⋯」，破折號用「——」，各佔兩個字的位置。
- 書名、法規名用《》，篇名、章名用〈〉；並列的詞語用頓號「、」。
- 英文、數字、指令、路徑與網址保持半形；整句英文用半形標點。
- 本模板慣例：中文與英文、數字之間留一個半形空格。

## 授權聲明

本指引的「原則」「保護清單」「刪除 AI 痕跡」「台灣用語」與「標點」整理自 speak-human-tw v1.4.0（commit `72279f8`），依下列 MIT 授權使用：

```text
MIT License

Copyright (c) 2026 Raymond Hou (雷蒙三十)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
