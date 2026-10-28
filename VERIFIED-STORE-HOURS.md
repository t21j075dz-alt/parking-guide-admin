# 営業時間確認台帳（2026年10月28日）

卒業研究・駐車場案内アプリの施設マスターに反映した営業時間と公開情報の出典です。

- 研究対象 **210施設** のうち、**36施設**に根拠のある営業時間を登録しました。残りの実店舗は**未確認**として保持し、推定による「営業中／休」の自動判定をしません。
- 別に「道の駅日光（録画実験）」の**現地参考営業時間**を表示しています。録画実験の現在地を本物の日光市の施設に置き換えることはしません。
- 時間・出典URL・確認日・売場別の注意点は、各施設の `operations` に保存し、**管理画面（facility-catalog.js / facility-catalog.json）**と**利用者画面（facilities.js）**で同じ情報を使用します。
- 出典元の営業時間は事前予告なしに変更される場合があります。祝日・年末年始・棚卸・改装・災害等の臨時変更は別途最新案内を確認してください。
- **祝日が平日とは異なる店舗**の祝日自動判定は未実装です。対象店舗では `notes` に土日祝の条件を残しています。
- **毎月第1月曜・第3火曜**など、月内の位置で変わる定休日は現行判定に未対応です。誤った案内を防ぐため、そのような施設は `weeklyHours: null` として営業時間を参考表示だけにしています。
- `annualClosedDates` に登録済みの元日休業は、曜日ごとの営業時間より優先します。臨時休業の開始終了日時は `specialClosures`（ISO 8601形式、時差付き）として登録でき、曜日判定より優先します。ただし、確認できていない臨時休業を推測で登録しません。
- 駐車場の**入出庫可能時間**は店舗の営業時間と必ずしも一致しません。確認できた売場営業時間を駐車場のゲート開閉時間だと断定しないでください。
- 公式情報の修正は「営業時間・休業・共用区画」画面で上書きできます。手動編集した内容は公式確認済みデータと区別して保存します。

## 施設ごとの出典

| 施設ID | 店舗 | 営業時間・注記 | 公開情報 | 自動判定 |
| --- | --- | --- | --- | --- |
| `target_002` | ガスト 鳥取南店 | 平日8:00–23:30／土日祝7:00–23:30 | [確認元](https://store-info.skylark.co.jp/gusto/map/012867/) | 曜日判定対応 |
| `target_003` | 道の駅 西いなば気楽里 | 物販9:00–18:00（レストラン等は別） | [確認元](https://www.michi-no-eki.jp/stations/views/19931) | 曜日判定対応 |
| `target_004` | トライアル 米子大谷店 | 24時間営業（専門売場は別） | [確認元](https://www.trial-net.co.jp/shops/321/) | 曜日判定対応 |
| `target_007` | ラ・ムー 鳥取店 | 24時間営業 | [確認元](https://www.dkt-s.com/brand.html) | 曜日判定対応 |
| `target_008` | ラ・ムー 倉吉店 | 24時間営業 | [確認元](https://www.dkt-s.com/brand.html) | 曜日判定対応 |
| `target_009` | ホームプラザナフコ 東鳥取店 | 本館8:00–19:30（Nガーデン館8:00–19:00） | [確認元](https://www.nafco.life/shop_list/4370/) | 曜日判定対応 |
| `target_012` | ガスト 島根大田店 | 平日8:00–23:00／土日祝7:00–23:00 | [確認元](https://store-info.skylark.co.jp/gusto/map/012744/) | 曜日判定対応 |
| `target_018` | ラ・ムー 安来店 | 24時間営業 | [確認元](https://www.dkt-s.com/brand.html) | 曜日判定対応 |
| `target_019` | ホームプラザナフコ 松江店 | ホームセンター8:00–19:30（家具10:00–19:30） | [確認元](https://www.nafco.life/shop_list/1610/) | 曜日判定対応 |
| `nikko-test-001` | 道の駅日光 日光街道ニコニコ本陣 | 現地参考：ニコニコマルシェ9:00–18:00（第3火曜休） | [確認元](https://www.nikko-honjin.jp/access/) | 参考表示のみ |
| `target_021` | マルナカ 中井町店 | 24時間営業 | [確認元](https://www.the-fuji.com/store/okayama/) | 曜日判定対応 |
| `target_022` | ラ・ムー 岡山中央店 | 7:00–24:00（施設内テナントは別） | [確認元](https://job-gear.net/daikokuten2/AC0322291737/MDkyujin_d.htm) | 曜日判定対応 |
| `target_023` | トライアル 岡山豊浜店 | 24時間営業（ドラッグ9:00–21:00） | [確認元](https://www.trial-net.co.jp/shops/763/) | 曜日判定対応 |
| `target_024` | マルナカ 芳田店 | 8:00–23:00 | [確認元](https://www.the-fuji.com/store/okayama/) | 曜日判定対応 |
| `target_025` | マルナカ 総社店 | 10:00–22:00 | [確認元](https://www.the-fuji.com/mv/store/shop/okayama/m_soja.php) | 曜日判定対応 |
| `target_026` | マルナカ 大元店 | 7:00–24:00 | [確認元](https://www.the-fuji.com/store/okayama/) | 曜日判定対応 |
| `target_027` | マルナカ 雄町店 | 10:00–22:00 | [確認元](https://www.the-fuji.com/store/okayama/) | 曜日判定対応 |
| `target_029` | ガスト 岡山下中野店 | 8:00–23:30 | [確認元](https://store-info.skylark.co.jp/gusto/map/011956/) | 曜日判定対応 |
| `target_030` | 道の駅 久米の里 | 売店9:30–18:00／食堂11:00–14:00（土日祝15:00まで）・第1月曜休 | [確認元](https://www.okayama-kanko.jp/spot/detail_10567.html) | 参考表示のみ |
| `target_051` | マルキョウ 花見店 | 9:30–22:00 | [確認元](https://www.marukyo-web.co.jp/shop/756/) | 曜日判定対応 |
| `target_052` | トライアル 古賀花見店 | 24時間営業 | [確認元](https://www.trial-net.co.jp/shops/675/) | 曜日判定対応 |
| `target_053` | ハンズマン 大野城店 | 7:00–22:00（元日休業） | [確認元](https://www.handsman.co.jp/shop/onojo/) | 曜日判定対応 |
| `target_054` | ハンズマン くさみ店 | 7:30–22:00（元日休業） | [確認元](https://www.handsman.co.jp/shop/) | 曜日判定対応 |
| `target_057` | ジョイフル 福岡福津店 | 24時間営業 | [確認元](https://www.joyfull.co.jp/shop/305) | 曜日判定対応 |
| `target_058` | コメリパワー 飯塚店 | 本館9:00–20:00（資材館は日曜以外7:00–20:00） | [確認元](https://www.komeri.com/shop/storeSearch/StoreDetail.aspx?ID=1023) | 曜日判定対応 |
| `target_060` | マルキョウ 宗像店 | 9:30–22:00 | [確認元](https://www.marukyo-web.co.jp/shop/765/) | 曜日判定対応 |
| `target_121` | TRIAL smart 糸島荻浦店 | 24時間営業 | [確認元](https://www.trial-net.co.jp/shops/717/) | 曜日判定対応 |
| `target_122` | スーパーセンタートライアル 那珂川店 | 24時間営業 | [確認元](https://www.trial-net.co.jp/shops/369/) | 曜日判定対応 |
| `target_123` | TRIAL smart 筑紫野店 | 24時間営業 | [確認元](https://www.trial-net.co.jp/shops/532/) | 曜日判定対応 |
| `target_124` | TRIAL smart 福津店 | 24時間営業（ドラッグ9:00–21:00） | [確認元](https://www.trial-net.co.jp/shops/754/) | 曜日判定対応 |
| `target_125` | スーパーセンタートライアル 宗像店 | 24時間営業 | [確認元](https://www.trial-net.co.jp/shops/178/) | 曜日判定対応 |
| `target_126` | スーパーセンタートライアル 須恵店 | 24時間営業（専門売場は別） | [確認元](https://www.trial-net.co.jp/shops/473/) | 曜日判定対応 |
| `target_127` | スーパーセンタートライアル 宇美店 | 24時間営業 | [確認元](https://www.trial-net.co.jp/shops/6/) | 曜日判定対応 |
| `target_128` | TRIAL smart 粕屋店 | 24時間営業 | [確認元](https://www.trial-net.co.jp/shops/57/) | 曜日判定対応 |
| `target_130` | ホームプラザナフコ 前原店 | 8:00–19:00 | [確認元](https://www.nafco.life/shop_list/0460/) | 曜日判定対応 |
| `target_103` | ハンズマン 柳丸店 | 7:30–22:00（元日休業） | [確認元](https://www.handsman.co.jp/shop/yanagimaru/) | 曜日判定対応 |
| `target_111` | ハンズマン 宇宿店 | 7:00–22:00（元日休業） | [確認元](https://www.handsman.co.jp/shop/usuki/) | 曜日判定対応 |

## 研究上の注意

1. ラ・ムータウン岡山中央は7店舗の複合施設であり、ラ・ムーの営業時間を他のテナントへ一律に適用しません。個別の店舗が確認できたら、店舗ごとの `destinations[].operations` に別途追加してください。
2. 道の駅・ホームセンター・トライアル等は飲食店、資材館、家具売場、ドラッグ売場と本館で時間が異なる場合があります。`hoursLabel` と `notes` に区別を残しています。
3. `closed: true` は手動休業を優先します。未確認で `weeklyHours` がない場合は「営業時間未登録・確認できない」と区別します。
4. 更新日を再確認したら `hoursVerifiedAt` と出典URLを更新してください。2026年10月28日時点の確認は、その日付以降の継続営業を保証するものではありません。
