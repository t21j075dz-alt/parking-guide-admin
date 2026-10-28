# 駐車場案内システム 営業時間確認台帳

**確認日：2026年10月28日（日本時間）**

## 登録状況と品質基準

- 研究対象 **210/210店舗**について、個別店舗と照合できる営業時間・出典URLを記録済みです。
- **202店舗**で曜日別営業時間の自動表示が可能です。**8店舗は参考表示のみ**（季節で変わる営業時間・第3水曜休業・旧災害情報との不一致など）。
- 出典の種類は `hoursVerification` に格納。**official** は店舗運営の公式ページ、**government** は自治体・国土交通省など、**secondary** はチラシ掲載サイト・取扱メーカーの店舗検索・地図等の二次情報です。二次情報は別途、店舗公式情報との再照合を推奨します。
- 対象外に「道の駅日光（録画実験）」と「自宅駐車場（実験）」等があります。録画実験の所在地を実際の日光市の駐車場として公開しません。
- **営業時間≠駐車場の入出庫可能時間**です。商業施設の本館、ドラッグ・家具・資材売場、テナントも異なる場合があります。施設ごとの `notes` を必ず参照してください。

## 自動判定仕様

- `weeklyHours` は日曜 `0` ～ 土曜 `6` の曜日別区間です。開始と終了が同じ `00:00–00:00` は24時間営業。
- 年中の特定日休業は `annualClosedDates`、日時指定の改装・棚卸休業は `specialClosures` で通常営業に優先します。
- 第2・第4水曜休業、毎月第3水曜休業や12～2月冬季短縮営業など、現在の判定機能が扱えない条件は `weeklyHours:null` で参考表示に留めます。「未確認」「参考」を勝手に「営業中」とはしません。
- **日本の祝日による曜日切り替えや特別営業時間は未実装**。祝日が土日と同じ営業時間のガスト等は備考参照。
- 個別の一時休業や年末年始、天災等により営業時間が変わる場合があります。最新の公式情報を優先してください。
- ブラウザの管理画面で営業時間を変更したときは `hoursVerification:"manual"` として公式調査と区別します。

## 店舗別の時間と根拠

| ID | 研究対象店舗 | 営業時間の表示 | 自動状態 | 出典区分 | 出典URL | 売場・定休日・臨時休業の注意 |
|---|---|---|---|---|---|---|
| `target_001` | ドラッグストアコスモス 南昭和店 | 10:00–21:00 | 自動判定 | secondary | [参照](https://www.shufoo.net/pntweb/shopDetail/865711/14453253094503/) | 2026年10月15日〜29日の掲載店舗ページで同じ住所・時間を確認 |
| `target_002` | ガスト 鳥取南店 | 平日8:00–23:30／土日祝7:00–23:30 | 自動判定 | official | [参照](https://store-info.skylark.co.jp/gusto/map/012867/) | 祝日は土日と同じ営業時間。祝日自動判定には未対応 |
| `target_003` | 道の駅 西いなば気楽里 | 物販9:00–18:00（レストラン等は別） | 自動判定 | official | [参照](https://www.michi-no-eki.jp/stations/views/19931) | 物販の時間。飲食・コンビニなどは別営業時間 |
| `target_004` | トライアル 米子大谷店 | 24時間営業（専門売場は別） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/321/) | サービスカウンター9–21時、家電・ドラッグ9–22時 一時休業: 2026-10-28T22:00:00+09:00〜2026-10-29T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_005` | トライアル 琴浦店 | 24時間営業（ドラッグ9–20） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/176/) | ドラッグ9:00–20:00。サービスカウンター9:00–22:00 一時休業: 2026-11-06T22:00:00+09:00〜2026-11-07T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_006` | トライアル 境港店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/349/) | ドラッグ9:00–21:00 |
| `target_007` | ラ・ムー 鳥取店 | 24時間営業 | 自動判定 | official | [参照](https://www.dkt-s.com/brand.html) | — |
| `target_008` | ラ・ムー 倉吉店 | 24時間営業 | 自動判定 | official | [参照](https://www.dkt-s.com/brand.html) | — |
| `target_009` | ホームプラザナフコ 東鳥取店 | 本館8:00–19:30（Nガーデン館8:00–19:00） | 自動判定 | official | [参照](https://www.nafco.life/shop_list/4370/) | 本館の営業時間を営業判定に使用。Nガーデン館は19:00まで |
| `target_010` | カインズFC 鳥取店 | 09:00–20:00 | 自動判定 | official | [参照](https://map.cainz.com/detail/154/) | 本館09:00–20:00、資材館は月〜土07:00–20:00、日曜09:00–20:00。1月1日休業 固定休業日: 01-01; |
| `target_011` | ドラッグストアコスモス 大田店 | 10:00–21:00 | 自動判定 | secondary | [参照](https://xn--pssw6iv2y.com/shop/cosmosoda) | 大田市の店舗紹介ページと電話番号一致、公式店舗ページは別途要確認 |
| `target_012` | ガスト 島根大田店 | 平日8:00–23:00／土日祝7:00–23:00 | 自動判定 | official | [参照](https://store-info.skylark.co.jp/gusto/map/012744/) | 祝日は土日と同じ営業時間。祝日自動判定には未対応 |
| `target_013` | 道の駅 湯の川 | 売店9:00–17:30（冬季短縮あり・不定休／参考） | 参考表示 | government | [参照](https://www.kankou-shimane.com/destination/21682) | 冬季は短縮あり・不定休。駐車場/トイレは24時間利用可（売店の営業時間をゲート制限に用いない） |
| `target_014` | トライアル 雲南店 | 24時間営業（ドラッグ10–19） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/440/) | ドラッグ10:00–19:00 |
| `target_015` | トライアル 浜田店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/40/) | ドラッグ9:00–22:00 |
| `target_016` | トライアル 益田店 | 24時間営業（ドラッグ9–19） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/401/) | ドラッグ9:00–19:00 |
| `target_017` | トライアル 大田店 | 24時間営業（ドラッグ9–19） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/751/) | ドラッグ9:00–19:00 一時休業: 2026-11-13T22:00:00+09:00〜2026-11-14T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_018` | ラ・ムー 安来店 | 24時間営業 | 自動判定 | official | [参照](https://www.dkt-s.com/brand.html) | — |
| `target_019` | ホームプラザナフコ 松江店 | ホームセンター8:00–19:30（家具10:00–19:30） | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1610/) | 家具売場は10:00から。資材館は別店舗として掲載 |
| `target_020` | ホームプラザナフコ 北出雲店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1600/) | — |
| `target_021` | マルナカ 中井町店 | 24時間営業 | 自動判定 | official | [参照](https://www.the-fuji.com/store/okayama/) | — |
| `target_022` | ラ・ムー 岡山中央店 | 7:00–24:00（施設内テナントは別） | 自動判定 | official | [参照](https://job-gear.net/daikokuten2/AC0322291737/MDkyujin_d.htm) | 運営会社の採用情報で確認。ユニクロ・GUなど施設内の他店舗へは適用しない |
| `target_023` | トライアル 岡山豊浜店 | 24時間営業（ドラッグ9:00–21:00） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/763/) | ドラッグ売場9:00–21:00 一時休業: 2026-11-10T22:00:00+09:00〜2026-11-11T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_024` | マルナカ 芳田店 | 8:00–23:00 | 自動判定 | official | [参照](https://www.the-fuji.com/store/okayama/) | — |
| `target_025` | マルナカ 総社店 | 10:00–22:00 | 自動判定 | official | [参照](https://www.the-fuji.com/mv/store/shop/okayama/m_soja.php) | — |
| `target_026` | マルナカ 大元店 | 7:00–24:00 | 自動判定 | official | [参照](https://www.the-fuji.com/store/okayama/) | — |
| `target_027` | マルナカ 雄町店 | 10:00–22:00 | 自動判定 | official | [参照](https://www.the-fuji.com/store/okayama/) | — |
| `target_028` | ドラッグストアコスモス 津高店 | 10:00–21:00 | 自動判定 | secondary | [参照](https://www.shufoo.net/pntweb/shopDetail/853123/55463252971452/) | 2026年10月15日〜29日の店舗広告と住所一致 |
| `target_029` | ガスト 岡山下中野店 | 8:00–23:30 | 自動判定 | official | [参照](https://store-info.skylark.co.jp/gusto/map/011956/) | — |
| `target_030` | 道の駅 久米の里 | 売店9:30–18:00／食堂11:00–14:00（土日祝15:00まで）・第1月曜休 | 参考表示 | official | [参照](https://www.okayama-kanko.jp/spot/detail_10567.html) | 毎月第1月曜（祝日なら翌日）と12/31–1/2休。月次定休は現行判定機能で未対応のため、営業時間は参考表示に限定 |
| `target_031` | ドラッグストアコスモス 福山新涯店 | 10:00–21:00 | 自動判定 | secondary | [参照](https://www.shiseido.co.jp/sw/navi/shopdetail.html?shopCd=615GU7) | 資生堂店舗取扱情報。元日休業と明記 固定休業日: 01-01; |
| `target_032` | ガスト 東広島西条インター店 | 09:00–23:30 | 自動判定 | official | [参照](https://store-info.skylark.co.jp/gusto/map/012886/) | — |
| `target_033` | 道の駅 たけはら | 物販9:00–17:00（第3水曜等休／参考） | 参考表示 | official | [参照](https://www.iine-takehara.com/michinoekitakehara-buying) | 1F物産コーナー。第3水曜と年末年始12/31〜1/3休業。祝日の場合は翌日。 |
| `target_034` | MrMax 八本松店 | 08:00–22:00 | 自動判定 | official | [参照](https://mrmax.co.jp/shops/0000000060/) | — |
| `target_035` | ホームプラザナフコ 東広島店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1530/) | ツーワンスタイルは09:00–20:00 |
| `target_036` | ホームプラザナフコ 三次店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2260/) | 資材館は通常08:00–19:00、11～2月は08:00–18:00。家具売場は10:00–20:00 |
| `target_037` | ホームプラザナフコ 尾道店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/4110/) | — |
| `target_038` | ホームプラザナフコ 黒瀬店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3000/) | — |
| `target_039` | ホームプラザナフコ 庄原店 | 08:00–18:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2890/) | — |
| `target_040` | ホームプラザナフコ 吉田店 | 08:30–18:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3890/) | — |
| `target_041` | ドラッグストアコスモス 新山口駅店 | 10:00–21:00 | 自動判定 | secondary | [参照](https://map.yahoo.co.jp/v3/place/s0QhrEECH1E) | Yahoo!地図の営業時間表示で確認、公式一次ページ要再確認 |
| `target_042` | ガスト 山口小郡店 | 09:00–23:00 | 自動判定 | official | [参照](https://store-info.skylark.co.jp/gusto/map/018642/) | — |
| `target_043` | 道の駅 あいお | 売店9:00–18:00（第2・第4水曜等休／参考） | 参考表示 | official | [参照](https://michinoeki-aio.com/guide/) | 第2・第4水曜休み（祝日は営業）、12/31〜1/3休み、臨時休業は営業日カレンダー参照。駐車場の利用可否とは別 |
| `target_044` | トライアル 新下関店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/85/) | ドラッグ9:00–22:00 |
| `target_045` | MrMax 山口店 | 09:00–20:00 | 自動判定 | official | [参照](https://mrmax.co.jp/shops/0000000024/) | 2026年10月19日～11月4日改装休業（店舗本体）。併設テナントは別営業 一時休業: 2026-10-19T00:00:00+09:00〜2026-11-05T00:00:00+09:00（改装のため店舗休業）; |
| `target_046` | MrMax 末武店 | 08:00–21:00 | 自動判定 | official | [参照](https://mrmax.co.jp/shops/0000000010/) | — |
| `target_047` | ホームプラザナフコ 山口店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0480/) | — |
| `target_048` | ホームプラザナフコ 周南店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3960/) | — |
| `target_049` | ホームプラザナフコ 防府店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0260/) | — |
| `target_050` | ホームプラザナフコ 南岩国店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1240/) | 家具売場は09:00–20:00 |
| `target_051` | マルキョウ 花見店 | 9:30–22:00 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/756/) | — |
| `target_052` | トライアル 古賀花見店 | 24時間営業 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/675/) | — |
| `target_053` | ハンズマン 大野城店 | 7:00–22:00（元日休業） | 自動判定 | official | [参照](https://www.handsman.co.jp/shop/onojo/) | 1月1日休業 固定休業日: 01-01; |
| `target_054` | ハンズマン くさみ店 | 7:30–22:00（元日休業） | 自動判定 | official | [参照](https://www.handsman.co.jp/shop/) | 1月1日休業 固定休業日: 01-01; |
| `target_055` | カインズ 福岡新宮店 | 09:00–20:00 | 自動判定 | official | [参照](https://map.cainz.com/detail/828/) | 元日休業 固定休業日: 01-01; |
| `target_056` | ドラッグストアモリ 宗像店 | 09:00–00:00 | 自動判定 | official | [参照](https://www.doramori.co.jp/store/6618.html/) | — |
| `target_057` | ジョイフル 福岡福津店 | 24時間営業 | 自動判定 | official | [参照](https://www.joyfull.co.jp/shop/305) | — |
| `target_058` | コメリパワー 飯塚店 | 本館9:00–20:00（資材館は日曜以外7:00–20:00） | 自動判定 | official | [参照](https://www.komeri.com/shop/storeSearch/StoreDetail.aspx?ID=1023) | 本館を判定。資材館は日曜以外7:00から |
| `target_059` | 道の駅 香春 | 09:00–18:00 | 自動判定 | official | [参照](https://michinoeki-kawara.jp/) | 物産直売所9:00–18:00、飲食9:00–17:00、トイレは24時間利用可。1月1～3日休業 固定休業日: 01-01,01-02,01-03; |
| `target_060` | マルキョウ 宗像店 | 9:30–22:00 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/765/) | — |
| `target_061` | ドラッグストアモリ 神埼本堀店 | 09:00–00:00 | 自動判定 | official | [参照](https://www.doramori.co.jp/store/12491.html/) | — |
| `target_062` | ガスト 佐賀兵庫店 | 08:00–23:30 | 自動判定 | official | [参照](https://store-info.skylark.co.jp/gusto/map/012863/) | — |
| `target_063` | 道の駅 大和 そよかぜ館 | 09:00–18:00 | 自動判定 | government | [参照](https://www.asobo-saga.jp/spots/detail/f3b63766-7ca9-43ea-a29f-76f5cb4a189d) | 物産9:00–18:00。1月1～3日休業。トイレ・駐車場は24時間利用可 固定休業日: 01-01,01-02,01-03; |
| `target_064` | TRIAL smart 伊万里店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/83/) | ドラッグ9:00–21:00 |
| `target_065` | トライアル 武雄富岡店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/399/) | 家電9:00–22:00／ドラッグ9:00–22:00 一時休業: 2026-11-02T22:00:00+09:00〜2026-11-03T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_066` | マルキョウ 神埼店 | 09:30–22:00 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/662/) | — |
| `target_067` | マルキョウ 武雄店 | 09:30–21:00 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/650/) | — |
| `target_068` | MrMax 北茂安店 | 10:00–22:00 | 自動判定 | official | [参照](https://mrmax.co.jp/shops/0000000022/) | — |
| `target_069` | ホームプラザナフコ 武雄店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1380/) | — |
| `target_070` | ホームプラザナフコ 唐津店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0500/) | 家具館10:00–19:30 |
| `target_071` | ドラッグストアコスモス 大潟店 | 10:00–21:00 | 自動判定 | secondary | [参照](https://www.shufoo.net/pntweb/shopDetail/910812/) | 2026年10月15日〜29日の店舗広告 |
| `target_072` | ガスト 長崎大浦海岸店 | 07:00–23:30 | 自動判定 | official | [参照](https://store-info.skylark.co.jp/gusto/map/018579/) | — |
| `target_073` | 道の駅 彼杵の荘 | 物販8:00–17:30（12/31午前のみ・1/1〜3休／参考） | 参考表示 | government | [参照](https://www.qsr.mlit.go.jp/n-michi/michi_no_eki/kobetu/sonogi/sonogi.html) | 物産8:00–17:30、食堂11:00–14:00、屋台9:00–16:00。12/31物産は午前中のみ、元日～3日休業 |
| `target_074` | トライアル 佐世保大和店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/184/) | ドラッグ9:00–22:00 |
| `target_075` | トライアル 島原店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/347/) | ドラッグ9:00–22:00 |
| `target_076` | トライアル 大村店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/96/) | ドラッグ9:00–22:00 |
| `target_077` | トライアル 諫早店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/331/) | ドラッグ9:00–22:00 |
| `target_078` | トライアル 時津店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/388/) | ドラッグ9:00–22:00 |
| `target_079` | マルキョウ 大宮店 | 09:30–21:30 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/785/) | — |
| `target_080` | ホームプラザナフコ 時津店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2950/) | TWO-ONE売場は10:00–20:00、本館の営業時間を判定 |
| `target_081` | ドラッグストアコスモス 大津バイパス店 | 10:00–21:00 | 自動判定 | government | [参照](https://www.hapimon.jp/kiji0032408/index.html) | 熊本県子育て支援サイト、2025年3月31日確認、1月1日休業 固定休業日: 01-01; |
| `target_082` | ガスト 熊本戸島店 | 09:00–23:30／土日08:00–23:30 | 自動判定 | official | [参照](https://store-info.skylark.co.jp/gusto/map/012857/) | 祝日も土日と同じ8:00開店（祝日自動判定未対応） |
| `target_083` | 道の駅 大津 | 09:00–18:00 | 自動判定 | government | [参照](https://www.qsr.mlit.go.jp/n-michi/michi_no_eki/kobetu/ozu/ozu.html) | 物産・工芸館9:00–18:00、飲食10:00–18:00。1月1日休 固定休業日: 01-01; |
| `target_084` | メガセンタートライアル 荒尾店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/739/) | ドラッグ9:00–22:00 |
| `target_085` | トライアル 宇土店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/170/) | ドラッグ9:00–21:00。2026年10月3日から24時間営業再開と公式告知 |
| `target_086` | トライアル 八代店 | 公式店舗ページ24時間表示（地震後の変更履歴あり・要再確認） | 参考表示 | official | [参照](https://www.trial-net.co.jp/shops/120/) | 2026年8月の公式地震情報は7:00–24:00。店舗ページは24時間表示のため営業状態は未確定として扱う |
| `target_087` | カインズ 熊本宇土店 | 09:00–20:00 | 自動判定 | official | [参照](https://map.cainz.com/detail/840/) | 元日休業。震災後2026年8月10日から9:00–20:00で運営と公式記載 固定休業日: 01-01; |
| `target_088` | マルキョウ 植木店 | 09:30–21:00 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/672/) | — |
| `target_089` | マルキョウ 合志店 | 09:30–22:00 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/664/) | — |
| `target_090` | マルキョウ 玉名店 | 09:30–22:00 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/658/) | — |
| `target_091` | ドラッグストアコスモス 大分新川店 | 10:00–21:00 | 自動判定 | official | [参照](https://www.cosmospc.co.jp/shop/shop-search.html?city=oita&pref=oita) | — |
| `target_092` | ガスト 大分森町店 | 08:00–00:00 | 自動判定 | official | [参照](https://store-info.skylark.co.jp/gusto/map/012954/) | — |
| `target_093` | 道の駅 童話の里くす | 直売3〜11月9:00–18:00／12〜2月9:00–17:00（参考） | 参考表示 | official | [参照](https://kusumichi.jp/) | 3月〜11月は9:00–18:00、12月〜2月は9:00–17:00。レストラン11:00–15:30。年末年始は要確認 |
| `target_094` | トライアル 敷戸店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/445/) | ドラッグ9:00–21:00 |
| `target_095` | トライアル 日田店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/12/) | ドラッグ9:00–21:00 |
| `target_096` | トライアル 別府店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/128/) | ドラッグ9:00–22:00 |
| `target_097` | トライアル 中津店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/135/) | ドラッグ9:00–22:00 |
| `target_098` | マルキョウ 皆春店 | 09:30–22:00 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/295/) | — |
| `target_099` | マルキョウ 中津店 | 09:30–21:00 | 自動判定 | official | [参照](https://www.marukyo-web.co.jp/shop/660/) | — |
| `target_100` | MrMax 宇佐店 | 09:00–20:00 | 自動判定 | official | [参照](https://mrmax.co.jp/shops/0000000027/) | — |
| `target_101` | ドラッグストアモリ 恒久店 | 09:00–00:00 | 自動判定 | official | [参照](https://www.doramori.co.jp/store/1718.html/) | — |
| `target_102` | ジョイフル 宮崎大塚店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.joyfull.co.jp/shop/183) | — |
| `target_103` | ハンズマン 柳丸店 | 7:30–22:00（元日休業） | 自動判定 | official | [参照](https://www.handsman.co.jp/shop/yanagimaru/) | 1月1日休業 固定休業日: 01-01; |
| `target_104` | 道の駅 高岡ビタミン館 | 09:00–18:00 | 自動判定 | official | [参照](https://vitaminkan.miyazaki.jp/) | 宮崎市公式では1月1・2日休業。気象事情による営業時間変更あり 固定休業日: 01-01,01-02; |
| `target_105` | トライアル 加納店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/711/) | ドラッグ9:00–22:00 |
| `target_106` | トライアル 宮崎恒久店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/284/) | ドラッグ9:00–22:00 一時休業: 2026-11-04T22:00:00+09:00〜2026-11-05T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_107` | トライアル 都城都北店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/581/) | ドラッグ9:00–21:00 一時休業: 2026-11-06T22:00:00+09:00〜2026-11-07T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_108` | トライアル 小林店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/237/) | ドラッグ9:00–21:00 一時休業: 2026-11-02T22:00:00+09:00〜2026-11-03T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_109` | メガセンタートライアル 日向店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/483/) | ドラッグ9:00–21:00 |
| `target_110` | トライアル 日南店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/457/) | ドラッグ9:00–21:00 |
| `target_111` | ハンズマン 宇宿店 | 7:00–22:00（元日休業） | 自動判定 | official | [参照](https://www.handsman.co.jp/shop/usuki/) | 1月1日休業 固定休業日: 01-01; |
| `target_112` | ドラッグストアコスモス 鹿児島宇宿店 | 10:00–21:00 | 自動判定 | secondary | [参照](https://www.shiseido.co.jp/sw/navi/shopdetail.html?shopCd=616GR9) | 資生堂店舗取扱情報。元日休業と明記 固定休業日: 01-01; |
| `target_113` | ジョイフル 鹿児島坂之上店 | 08:00–01:00 | 自動判定 | official | [参照](https://www.joyfull.co.jp/shop/521) | 翌日午前1時まで営業 |
| `target_114` | 道の駅 たるみず | 売店9:00–19:00（第3水曜休／参考） | 参考表示 | official | [参照](https://mitinoeki-tarumizu.com/) | 道の駅たるみず湯っ足り館（牛根麓1038-1）。第3水曜全館休館（変動あり）。温泉は毎週水曜休（祝日は営業）。売店9:00–19:00、レストラン11:00–15:00。駐車場の開放時間とは別 |
| `target_115` | トライアル 指宿店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/776/) | 24時間営業／免税対応 一時休業: 2026-11-13T22:00:00+09:00〜2026-11-14T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_116` | トライアル 鹿屋店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/407/) | ドラッグ9:00–22:00 |
| `target_117` | ホームプラザナフコ 谷山店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1630/) | — |
| `target_118` | トライアル 出水黄金店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/419/) | ドラッグ9:00–21:00 |
| `target_119` | トライアル 加治木店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/569/) | ドラッグ9:00–21:00 |
| `target_120` | ホームプラザナフコ 鹿児島東開店 | 10:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3560/) | — |
| `target_121` | TRIAL smart 糸島荻浦店 | 24時間営業 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/717/) | — |
| `target_122` | スーパーセンタートライアル 那珂川店 | 24時間営業 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/369/) | — |
| `target_123` | TRIAL smart 筑紫野店 | 24時間営業 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/532/) |  一時休業: 2026-11-02T22:00:00+09:00〜2026-11-03T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_124` | TRIAL smart 福津店 | 24時間営業（ドラッグ9:00–21:00） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/754/) | ドラッグ売場9:00–21:00 一時休業: 2026-11-09T22:00:00+09:00〜2026-11-10T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_125` | スーパーセンタートライアル 宗像店 | 24時間営業（ドラッグ9–20） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/178/) | ドラッグ9:00–20:00（公式店舗ページ記載） 一時休業: 2026-10-29T22:00:00+09:00〜2026-10-30T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_126` | スーパーセンタートライアル 須恵店 | 24時間営業（専門売場は別） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/473/) | サービスカウンター・家電9–22時、ドラッグ9–21時 一時休業: 2026-10-28T22:00:00+09:00〜2026-10-29T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_127` | スーパーセンタートライアル 宇美店 | 24時間営業 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/6/) | — |
| `target_128` | TRIAL smart 粕屋店 | 24時間営業 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/57/) | — |
| `target_129` | TRIAL smart アクロスプラザ篠栗店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/718/) | ドラッグ9:00–21:00 |
| `target_130` | ホームプラザナフコ 前原店 | 8:00–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0460/) | — |
| `target_131` | ホームプラザナフコ 二丈店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1520/) | — |
| `target_132` | ホームプラザナフコ 元岡店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3930/) | — |
| `target_133` | ホームプラザナフコ 今宿店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0380/) | — |
| `target_134` | ホームプラザナフコ 春日フォレストシティ店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3140/) | ツーワンスタイルは09:00–20:00 |
| `target_135` | ホームプラザナフコ 筑紫店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1770/) | — |
| `target_136` | ホームプラザナフコ トリアス久山店 | 09:30–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1650/) | — |
| `target_137` | ホームプラザナフコ 篠栗店 | 08:00–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1100/) | — |
| `target_138` | ホームプラザナフコ 南那珂川店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2500/) | — |
| `target_139` | スーパーセンタートライアル 若松店 | 24時間営業 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/809/) | — |
| `target_140` | スーパーセンタートライアル 二島店 | 24時間営業（ドラッグ10–20） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/39/) | ドラッグ10:00–20:00。出店スペースの時間とは異なる |
| `target_141` | スーパーセンタートライアル 門司片上海岸店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/309/) | ドラッグ9:00–22:00 |
| `target_142` | スーパーセンタートライアル 北九州空港バイパス店 | 24時間営業（ドラッグ8–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/5/) | ドラッグ8:00–22:00 |
| `target_143` | スーパーセンタートライアル 西港店 | 24時間営業 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/44/) |  一時休業: 2026-10-29T22:00:00+09:00〜2026-10-30T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_144` | スーパーセンタートライアル 上津役店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/8/) | ドラッグ9:00–22:00 |
| `target_145` | スーパーセンタートライアル 苅田店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/315/) | ドラッグ9:00–22:00 |
| `target_146` | スーパーセンタートライアル 東水巻店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/472/) | ドラッグ9:00–21:00 |
| `target_147` | スーパーセンタートライアル 遠賀店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/158/) | ドラッグ9:00–21:00 |
| `target_148` | スーパーセンタートライアル 水巻店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/157/) | ドラッグ9:00–22:00 |
| `target_149` | スーパーセンタートライアル 行橋上津熊店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/398/) | ドラッグ9:00–22:00 |
| `target_150` | スーパーセンタートライアル 行橋店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/210/) | ドラッグ9:00–22:00 |
| `target_151` | スーパーセンタートライアル 豊前店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/9/) | ドラッグ9:00–21:00 |
| `target_152` | スーパーセンタートライアル 上毛店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/729/) | ドラッグ9:00–21:00 |
| `target_153` | ホームプラザナフコ 豊津店 | 07:30–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2600/) | — |
| `target_154` | ホームプラザナフコ 椎田店 | 08:30–18:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3200/) | — |
| `target_155` | ホームプラザナフコ 岡垣店 | 08:30–18:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3900/) | — |
| `target_156` | ホームプラザナフコ 中間店 | 08:00–18:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/4350/) | — |
| `target_157` | ホームプラザナフコ 学研都市ひびきの店 | 月～土7:00–20:00／日8:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2200/) | 日曜日08:00–20:00。祝日は月～土と同じ07:00–20:00（祝日自動判定は未対応） |
| `target_158` | ホームプラザナフコ 西若松店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1900/) | — |
| `target_159` | ホームプラザナフコ 馬場山店 | 08:30–18:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1150/) | — |
| `target_160` | ホームプラザナフコ 徳力店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0820/) | — |
| `target_161` | ホームプラザナフコ 中井店 | 08:00–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0900/) | — |
| `target_162` | ホームプラザナフコ 小倉南店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2560/) | ツーワンスタイルは09:00–20:00 |
| `target_163` | スーパーセンタートライアル 飯塚庄内店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/736/) | ドラッグ9:00–21:00 |
| `target_164` | TRIDRUG GO 目尾店 | 07:00–22:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/371/) | ドラッグ9:00–22:00 |
| `target_165` | スーパーセンタートライアル 上三緒店 | 24時間営業（ドラッグ9–20） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/50/) | ドラッグ9:00–20:00 |
| `target_166` | スーパーセンタートライアル 飯塚店 | 24時間営業（ドラッグ8–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/49/) | ドラッグ8:00–22:00 |
| `target_167` | TRIAL GO 飯塚幸袋店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/668/) | — |
| `target_168` | スーパーセンタートライアル 宮田店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/531/) | ドラッグ9:00–21:00 |
| `target_169` | TRIFOODS GO 宮若福丸店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/689/) | — |
| `target_170` | スーパーセンタートライアル 福智店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/393/) | ドラッグ9:00–21:00 |
| `target_171` | TRIDRUG GO 池尻店 | 00:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/353/) | ドラッグ8:00–22:00 |
| `target_172` | TRIAL GO 稲築店 | 06:00–00:00 | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/337/) | 06:00–24:00 一時休業: 2026-11-09T22:00:00+09:00〜2026-11-10T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_173` | スーパーセンタートライアル 桂川店 | 24時間営業（ドラッグ9–20） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/468/) | ドラッグ9:00–20:00 |
| `target_174` | スーパーセンタートライアル 鞍手店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/362/) | ドラッグ9:00–22:00 |
| `target_175` | スーパーセンタートライアル 小竹店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/310/) | ドラッグ9:00–21:00 一時休業: 2026-11-02T22:00:00+09:00〜2026-11-03T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_176` | スーパーセンタートライアル 直方店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/11/) | ドラッグ9:00–21:00 |
| `target_177` | スーパーセンタートライアル 田川後藤寺店 | 6:00–24:00（ドラッグ10–20） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/269/) | ドラッグ10:00–20:00 一時休業: 2026-11-06T22:00:00+09:00〜2026-11-07T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_178` | ホームプラザナフコ 稲築店 | 08:00–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2870/) | — |
| `target_179` | ホームプラザナフコ 宮田店 | 08:00–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1460/) | — |
| `target_180` | ホームプラザナフコ 田川店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0320/) | — |
| `target_181` | ホームプラザナフコ 川崎店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1510/) | — |
| `target_182` | ホームプラザナフコ 直方店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/4500/) | — |
| `target_183` | ホームプラザナフコ 鞍手店 | 07:30–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3460/) | — |
| `target_184` | ホームプラザナフコ 飯塚南店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0690/) | 資材館は06:30–20:00。ツーワンスタイルは10:00–20:00 |
| `target_185` | ホームプラザナフコ 頴田店 | 08:30–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1330/) | — |
| `target_186` | スーパーセンタートライアル 甘木店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/100/) | ドラッグ9:00–21:00 |
| `target_187` | スーパーセンタートライアル 八女店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/130/) | ドラッグ9:00–21:00 |
| `target_188` | スーパーセンタートライアル 柳川西蒲池店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/403/) | ドラッグ9:00–21:00 |
| `target_189` | スーパーセンタートライアル 久留米店 | 24時間営業（ドラッグ8–20） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/116/) | ドラッグ8:00–20:00 一時休業: 2026-11-04T22:00:00+09:00〜2026-11-05T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_190` | スーパーセンタートライアル 久留米上津店 | 24時間営業（ドラッグ9–22） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/300/) | ドラッグ9:00–22:00 一時休業: 2026-10-28T22:00:00+09:00〜2026-10-29T09:30:00+09:00（棚卸のため臨時休業）; |
| `target_191` | コメリパワー 大牟田店 | 09:00–20:00 | 自動判定 | official | [参照](https://www.komeri.com/shop/storeSearch/StoreSelect.aspx?a_name=%E5%A4%A7%E7%89%9F%E7%94%B0%E5%B8%82&p_code=40) | 本館9:00–20:00、資材館（日曜除く）7:00–20:00。不定休・祝日の特別営業には別途確認が必要 |
| `target_192` | スーパーセンタートライアル 大刀洗店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/363/) | ドラッグ9:00–21:00 |
| `target_193` | スーパーセンタートライアル 筑後店 | 24時間営業（ドラッグ9–21） | 自動判定 | official | [参照](https://www.trial-net.co.jp/shops/37/) | ドラッグ9:00–21:00 |
| `target_194` | ホームプラザナフコ うきは店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/4080/) | — |
| `target_195` | ホームプラザナフコ 瀬高店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/hc/shop_list/2850/) | — |
| `target_196` | ホームプラザナフコ 大刀洗店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1790/) | — |
| `target_197` | ホームプラザナフコ 旗崎店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0420/) | 資材・DIY売場は06:30–20:00 |
| `target_198` | ホームプラザナフコ 南久留米店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2050/) | — |
| `target_199` | ホームプラザナフコ 城島店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3700/) | — |
| `target_200` | ホームプラザナフコ 八女店 | 08:00–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1180/) | 家具は10:00–19:00 |
| `target_201` | ホームプラザナフコ 黒木店 | 08:30–19:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3470/) | — |
| `target_202` | ホームプラザナフコ 八女インター店 | 07:30–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/4360/) | — |
| `target_203` | ホームプラザナフコ 大牟田店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0070/) | 家具は10:00–20:00 |
| `target_204` | ホームプラザナフコ 甘木インター店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1370/) | — |
| `target_205` | ホームプラザナフコ 杷木店 | 09:00–18:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/2860/) | — |
| `target_206` | ホームプラザナフコ 筑前店 | 08:00–19:30 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/3440/) | — |
| `target_207` | ホームプラザナフコ 柳川店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/0330/) | 家具売場は10:00–20:00 |
| `target_208` | ホームプラザナフコ 筑後店 | 08:00–20:00 | 自動判定 | official | [参照](https://www.nafco.life/shop_list/1290/) | — |
| `target_209` | コメリパワー 筑後店 | 09:00–20:00 | 自動判定 | official | [参照](https://www.komeri.com/shop/storeSearch/StoreDetail.aspx?ID=1028) | 本館9:00–20:00、資材館（日曜除く）7:30–20:00。不定休・祝日の特別営業には別途確認が必要 |
| `target_210` | コメリパワー うきは店 | 09:00–20:00 | 自動判定 | official | [参照](https://www.komeri.com/shop/storeSearch/StoreDetail.aspx?ID=1099) | 本館9:00–20:00、資材館（日曜除く）7:00–20:00。不定休・祝日の特別営業には別途確認が必要 |

## 今後の品質向上

1. 参考表示の8店舗について、第N曜日、祝日、季節の営業時間を正しく処理できるように実装・テストを追加すること。
2. 二次情報だけで確認できた店舗は運営公式ページを再確認し、出典分類を更新すること。
3. 店舗の営業時間と駐車場ゲートの開閉時間を別カラムに分けて管理し、駐車場を24時間利用できる施設の「休」表示を区別すること。
4. 変更・確認履歴を保持し、研究発表で検証方法・日時・不確実性を説明できるようにすること。
