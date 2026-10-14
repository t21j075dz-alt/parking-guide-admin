"use strict";
// Translate application labels only; input values and saved names stay untouched.
window.AdminI18n = (() => {
  const pairs = `駐車場マップ管理｜卒業研究|Parking map editor | Research
卒業研究・管理用|Research · Administration
駐車場マップ管理|Parking map editor
↶ 取り消す|↶ Undo
↷ やり直す|↷ Redo
ダークモード|Dark mode
ライトモード|Light mode
端末に保存|Save on device
バックアップを保存（JSON）|Save backup (JSON)
バックアップを開く（JSON）|Open backup (JSON)
配布用データを保存（JS）|Export app data (JS)
編集する施設|Choose a facility
施設を検索|Find a facility
施設名・住所|Facility name or address
都道府県|Prefecture
施設|Facility
ユーザーアプリへ自動反映|Sync to user app
クラウド連携は未設定です。|Cloud sync is not configured.
管理者メール|Administrator email
パスワード|Password
クラウドにログイン|Sign in to cloud
今すぐ反映|Sync now
クラウドから読込|Load from cloud
ログアウト|Sign out
ログイン中は編集内容を約1秒後に自動保存します。|While signed in, edits sync automatically after about one second.
敷地・建物・外周道路|Site, buildings and nearby roads
店舗建物|Store building
汎用建物|Other building
任意の建物|Other building
駐車場敷地|Parking area
対象外駐車場敷地|Excluded parking area
対象外駐車場|Excluded parking area
選択した店舗建物を追加|Add selected building
国道|National road
県道|Prefectural road
公道|Public road
「頂点を編集」で頂点を動かす。辺の＋で頂点追加。|Choose Edit vertices to move points. Use + on an edge to add a point.
駐車区画|Parking space
区画種類|Space type
普通車|Standard car
軽自動車|Kei car
車いす使用者用|Accessible
車椅子使用者用|Accessible
優先（高齢者・妊産婦等）|Priority parking
駐車枠を追加|Add parking space
初期寸法は現地に合わせて調整。専用枠は普通車に案内しません。|Adjust dimensions to the site. Dedicated spaces require matching search conditions.
通路・道路|Paths and roads
車道（双方向）|Two-way road
場内車道|Internal road
一方通行|One-way road
歩道|Footpath
横断歩道|Crosswalk
停止線|Stop line
速度抑制ハンプ|Speed bump
道路標識|Road sign
車両進入禁止|No entry
進入禁止|No entry
一時停止|Stop
施設・設備|Entrances and facilities
建物出入口|Building entrance
店舗入口|Store entrance
駐車場入口|Parking entrance
駐車場出口|Parking exit
駐車場出入口|Parking access
カート置き場|Cart return
駐輪場|Bicycle parking
二輪車置場|Motorcycle parking
荷捌きスペース|Loading area
EV充電器|EV charger
路面標示|Pavement markings
種類|Type
標示を追加|Add marking
配置物一覧|Objects
配置図|Map editor
枠を選んで移動・サイズ変更。細かな調整は右側へ。|Select a space to move or resize it. Use the right panel for details.
幅|Width
高さ|Height
長さ|Length
航空写真・縮尺|Aerial photo and scale
写真から縮尺を設定|Use photo scale
航空写真を表示|Show aerial photo
写真を動かす|Move photo
写真調整を終了|Finish moving photo
現在地を中心にする|Use my location
店舗位置へ戻す|Return to facility
写真の濃さ|Photo opacity
緯度・経度を直接指定する|Enter coordinates
背景|Background
なし|None
国土地理院・全国最新写真|GSI · Latest aerial photos
国土地理院・オルソ画像（別写真を試す）|GSI · Orthophoto (alternative)
国土地理院・簡易空中写真（別写真を試す）|GSI · Aerial photo (alternative)
緯度|Latitude
経度|Longitude
ズーム|Zoom
数値を反映|Apply values
写真を表示し、必要なときだけ位置を調整します。|Show a photo, then adjust its position if needed.
出典：|Source:
国土地理院|Geospatial Information Authority of Japan
· 写真の縮尺は概算です。|· Photo scale is approximate.
編集モード|Editing mode
移動|Move
サイズ変更|Resize
頂点を編集|Edit vertices
編集範囲全体|Fit editing area
配置に合わせる|Fit objects
ドラッグで移動・白いハンドルでサイズ変更|Drag to move. Use white handles to resize.
ドラッグで移動。白いハンドルでサイズ変更。|Drag to move. Use white handles to resize.
位置合わせ・方眼・一括変更|Alignment, grid and bulk resize
方眼を表示|Show grid
方眼にそろえる|Align to grid
近くの枠にそろえる|Align to nearby spaces
近くの辺にそろえる|Align to nearby edges
背景図形をロック|Lock background shapes
点を水平・垂直にそろえる|Align vertices horizontally / vertically
方眼の間隔|Grid spacing
通常は自由に動かせます。位置をそろえたいときだけチェックを入れてください。|Movement is free by default. Enable alignment only when needed.
Alt：位置合わせを一時OFF · 矢印：1cm · Shift：10cm · 中ボタン：画面移動|Alt: bypass alignment · Arrows: 1 cm · Shift: 10 cm · Middle mouse: pan
配置全体|All objects
一括サイズ変更|Resize all objects
選択中の設定|Selected object
大きさ（m）|Dimensions (m)
寸法を適用|Apply dimensions
区画種類の初期寸法に戻す|Reset to type dimensions
色|Color
枠や建物をクリックして選択してください。|Click a space or building to select it.
名称|Name
英語の名称（任意）|English name (optional)
EN表示に使用します。未入力の固有名は元の名称を表示します。|Used in English view. Custom names without a translation stay unchanged.
数値で微調整|Precise values
内部ID|Object ID
回転|Rotation
番号|Number
列・区画名|Row / area name
呼び方|Label format
列（A列）|Row (Row A)
区画（A区画）|Area (Area A)
表示：|Preview:
枠に表示する文字|Space label
枠の英語表記（任意）|English space label (optional)
例：福祉送迎専用|e.g. Assisted transport
状態|Status
空き|Available
使用中|Occupied
利用不可・判定不能|Unavailable / unknown
区画線の形|Line style
写真風（奥側閉じ・手前開き）|Closed at top, open at bottom
四辺・一本線|Four sides · single line
コの字（3辺線）|Three sides
両側線のみ|Side lines only
上辺だけ|Top line only
上辺の短い線|Short top corner lines
左側一本線|Left line only
右側一本線|Right line only
四辺・二重線|Four sides · double line
両側・二重線|Double side lines
四隅L字|Four L-shaped corners
二重線・先端丸型|Double lines · rounded ends
T字・端部印|T-shaped end marks
破線枠|Dashed outline
斜線入り枠|Hatched space
区画線なし|No outline
線色|Line color
太さ|Line thickness
上辺は回転前の上側です。線も枠と一緒に回転します。|Top means the top edge before rotation. Lines rotate with the space.
連続数|Number to add
選択中の枠と同じ大きさ・向きで、隙間なく追加します。|Add adjoining spaces with the same size and rotation.
↑ 上|↑ Above
← 左|← Left
右 →|Right →
↓ 下|↓ Below
車道|Road
通行方向|Traffic direction
双方向|Two-way
一方通行（矢印方向）|One-way (arrow direction)
一方通行の向きは「回転」で調整します。0°では右向きです。|Use Rotation to change direction. 0° points right.
建物|Building
店舗・建物|Store / building
建物ID|Building ID
建物サイズに合わせて文字を自動調整|Fit text to building
文字サイズの上限|Maximum text size
複合施設の店舗を選ぶと、名称と建物IDをまとめて反映します。|Selecting a store sets its name and building ID.
標識種類|Sign type
国道番号の標識|National route number
都道府県道番号の標識|Prefectural route number
路線番号|Route number
都道府県名|Prefecture name
道路に関連付けた一時停止標識には停止線と文字を表示します。|A stop sign linked to a road adds a stop line and label.
用途|Purpose
出入口|Entrance / exit
入口専用|Entrance only
出口専用|Exit only
入口と出口を別々に配置する場合は、それぞれ専用として設定してください。|For separate entrances and exits, set each to its own purpose.
入口種類|Entrance type
正面入口|Main entrance
その他の一般入口|Other public entrance
バリアフリー入口|Accessible entrance
従業員入口|Staff entrance
その他|Other
利用者が使用可能|Open to visitors
車椅子で利用可能|Wheelchair accessible
案内基準として使用|Use as guidance destination
関連建物ID|Linked building ID
複合施設では、目的店舗に対応する建物IDを選択してください。|Select the building ID for the destination store.
複製|Duplicate
削除|Delete
端末内に自動保存 · ログイン中はクラウドへ反映 ·|Saved on device automatically · Cloud sync while signed in ·
図形・寸法の出典|Design and dimension sources
ドラッグ：移動 · 白いハンドル：サイズ · Alt：位置合わせを一時OFF|Drag: move · White handles: resize · Alt: bypass alignment
白いハンドルでサイズ変更。Altで位置合わせを一時OFF。|Use white handles to resize. Hold Alt to bypass alignment.
頂点をドラッグ。辺の＋で追加、頂点をダブルクリックで削除。|Drag a vertex. Use + to add one. Double-click a vertex to delete it.
端末に保存しました。|Saved on this device.
端末に保存できませんでした。ページを閉じる前にJSON出力でバックアップしてください。|Could not save on this device. Export a JSON backup before closing.
幅・長さは正の数値で入力してください。|Enter positive width and length values.
先に航空写真を表示してください。|Show an aerial photo first.
写真の縮尺を採用しました。既存の枠は移動せず、新しい枠から実寸で追加します。|Photo scale applied. Existing spaces stay in place; new spaces use physical dimensions.
緯度・経度を入力してください。|Enter latitude and longitude.
このブラウザーでは現在地を取得できません。|Location is not supported by this browser.
現在地を取得しています…|Getting your location…
現在地を取得できませんでした。緯度・経度を直接入力してください。|Location unavailable. Enter coordinates manually.
該当する施設がありません。|No matching facilities.
ログイン済みです。編集内容は自動反映されます。|Signed in. Edits sync automatically.
クラウド連携設定済みです。管理者ログインが必要です。|Cloud sync is configured. Sign in as administrator.
番号は1〜8桁の数字で入力してください。|Enter a number with 1–8 digits.
同じ列・区画内で番号が重複しています。別の番号を入力してください。|This number already exists in the row or area. Choose another.
直進|Straight ahead
左折|Left turn
右折|Right turn
直進・左折|Straight / left
直進・右折|Straight / right
止まれ|STOP
徐行|SLOW
駐車禁止|NO PARKING
斜線帯|Hatched area
車いすマーク|Accessibility symbol
優先|Priority
EV充電|EV charging
車止め|Wheel stop
歩行者通路|Walkway
乗用車|Passenger cars
大型車・貨物車|Trucks and large vehicles
バス・キャンピングカー|Buses and RVs
二輪車・自転車|Motorcycles and bicycles
配慮・優先|Accessible and priority
充電|Charging
契約・利用者限定|Reserved and restricted
業務・短時間|Loading and short stay
表示専用・カスタム|Display areas and custom`;
  const extra = "カスタム（案内対象外）|Custom (not guided)\nバス|Buses\n乗降・管理専用（案内対象外）|Boarding / operational areas (not guided)\n二輪・自転車|Motorcycles and bicycles\n優先・配慮|Accessible and priority\n専用・契約|Dedicated and reserved\n荷さばき|Loading\n名称・寸法を現地に合わせて編集|Set label and dimensions to match the site\n国交省幅・福岡市推奨長さ|MLIT width / Fukuoka recommended length\n国交省指針|MLIT guideline reference\n大型車指針を初期値に採用|Initial size based on large-vehicle guidelines\n小型貨物車指針を初期値に採用|Initial size based on small-truck guidelines\n既存アプリ初期値|Existing app default\n既存アプリ初期値・現地条件|Existing default; check site requirements\n日本RV協会の推奨寸法|Japan RV Association recommended size\n普通乗用車指針を初期値に採用|Initial size based on passenger-car guidelines\n福岡市の基準を参考|Fukuoka City reference\n福岡市基準・小型貨物車指針|Fukuoka reference / small-truck guideline\n編集用仮寸法・現地確認|Provisional size; verify on site\n車いす用初期値を採用|Initial accessible-space dimensions\n魚沼市の例・地域基準を確認|Uonuma example; check local requirements\n航空写真を表示しました。「写真を動かす」で位置合わせできます。|Aerial photo shown. Choose Move photo to align it.\n写真調整中：航空写真をドラッグ、ホイールまたは＋/－で拡大縮小できます。|Drag the photo to align it. Use the wheel or + / − to zoom.\nオブジェクト編集に戻りました。|Returned to object editing.\n配置後の拡大は「表示倍率」を使ってください。写真倍率は固定しています。|Use display zoom after placing objects. Photo zoom is locked.\n配置後の拡大は表示倍率を使ってください。|Use display zoom after placing objects.\n航空写真を更新しました。背景を合わせてからオブジェクトを配置してください。|Photo updated. Align the background before placing objects.\n路線番号を入力すると、この道路の中央へ国道・県道標識を自動表示します。別の標識オブジェクトを置く必要はありません。|Enter a route number to show its sign on this road.\n一時停止・進入禁止は道路面の上へ移動すると、その道路に自動で関連付けます。|Move a Stop or No entry sign onto a road to link it.\n一時停止・進入禁止は道路上へ置くと自動で関連付けます。国道・県道を選択した場合は路線番号を道路内へ自動表示します。|Place Stop or No entry signs on a road to link them. Route numbers appear inside national and prefectural roads.\nクラウド連携は未設定です。sync-config.js を設定してください。|Cloud sync is not configured. Set up sync-config.js.\n単独施設では任意の建物IDを使用できます。|You can choose any building ID for a single-building facility.\nsync-config.js の Supabase 設定が必要です。|Configure Supabase in sync-config.js.\n管理者メールとパスワードを入力してください。|Enter the administrator email and password.\nログインしています…|Signing in…\nログインできませんでした。メール・パスワードとSupabase設定を確認してください。|Could not sign in. Check your credentials and Supabase settings.\nログインしました。以後の編集は自動反映されます。|Signed in. New edits sync automatically.\nログインできませんでした。ネットワーク接続を確認してください。|Could not sign in. Check your network connection.\nログインの有効期限が切れました。もう一度ログインしてください。|Your session expired. Sign in again.\nクラウド保存に失敗しました。SupabaseのRLS設定を確認してください。|Cloud save failed. Check Supabase access policies.\nクラウド保存に失敗しました。ネットワーク接続を確認してください。|Cloud save failed. Check your network connection.\nクラウドから読むには管理者ログインが必要です。|Sign in as administrator to load cloud data.\nクラウドから読み込んでいます…|Loading cloud data…\nクラウドから読み込めませんでした。|Could not load cloud data.\nレイアウト一覧が不正です。|Invalid layout collection.\n読み込み中に編集されたため反映を中止しました。編集を保存してから再読込してください。|Loading was cancelled because you made edits. Save them before reloading.\nクラウドから読み込めませんでした。接続とレイアウトデータを確認してください。|Could not load cloud data. Check the connection and layout data.\nクラウドからログアウトしました。端末内の編集データは残っています。|Signed out. Your local edits are still saved on this device.\nレイアウトJSONの形式が正しくありません。|Invalid layout JSON format.\n施設IDが一致しないか、objects が不足しています。|Facility ID mismatch or missing objects.\ncanvas は幅・高さを持つオブジェクトで指定してください。|Canvas must have width and height values.\nキャンバスの寸法・縮尺には正の数値が必要です。|Canvas dimensions and scale must be positive.\n航空写真の緯度・経度・ズームが不正です。|Invalid photo coordinates or zoom.\nオブジェクトのID・種類・座標が不正か、IDが重複しています。|Invalid object ID, type or coordinates, or duplicate IDs.\nオブジェクトの幅・高さには正の数値が必要です。|Object dimensions must be positive.\n回転角度には数値が必要です。|Rotation must be a number.\n多角形には数値座標の頂点が3個以上必要です。|A polygon needs at least three vertices with numeric coordinates.\n開業予定施設です。航空写真に完成店舗が写っていない場合があります。|Planned facility. Aerial photos may not show the completed building.\n";
  const dictionary = Object.fromEntries((pairs+'\n'+extra.trim()).split('\n').map(line=>{const i=line.indexOf('|');return [line.slice(0,i),line.slice(i+1)];}));
  const originals=new WeakMap();
  let observer;
  const english=()=>document.documentElement.lang==='en';
  function translate(text){
    if(!english())return text;
    if(dictionary[text])return dictionary[text];
    for(const preset of Object.values(window.ParkingMapDisplay.spacePresets))if(text===preset.label)return preset.en;
    const hint=text.match(/^(頂点をドラッグ。辺の＋で追加、頂点をダブルクリックで削除。) (.+)$/);
    if(hint)return translate(hint[1])+' This object has no editable vertices. Choose Resize to change its size.';
    if(text.startsWith('この敷地の目的店舗：'))return 'Destinations: '+text.slice('この敷地の目的店舗：'.length);
    const presetNote=text.match(/^([\d.]+ × [\d.]+ m)（幅×長さ） · (.+?)( · 空き枠案内の対象外)?$/);
    if(presetNote)return `${presetNote[1]} (width × length) · ${translate(presetNote[2])}${presetNote[3]?' · Not eligible for parking guidance':''}`;
    const linked=text.match(/^この標識は道路 (.+) に関連付け済みです。道路を動かしても追従します。$/);
    if(linked)return `Linked to road ${linked[1]}. Moves with the road.`;
    return text.replace(/^(\d+) 個$/,'$1 objects').replace('航空写真基準','Photo scale').replace('設定縮尺','Manual scale');
  }
  function apply(){
    observer?.disconnect();
    const walk=document.createTreeWalker(document.documentElement,NodeFilter.SHOW_TEXT);
    while(walk.nextNode()){
      const n=walk.currentNode;
      if(n.parentElement?.closest('script,style,textarea,#map-canvas,#facility-select,#facility-results,#facility-address'))continue;
      const last=originals.get(n),raw=last&&n.nodeValue===last.output?last.raw:n.nodeValue;
      const output=raw.replace(/\S[\s\S]*\S|\S/,part=>translate(part));
      if(n.nodeValue!==output)n.nodeValue=output;originals.set(n,{raw,output});
    }
    for(const el of document.querySelectorAll('[placeholder],[title],[aria-label],optgroup')){
      for(const attr of ['placeholder','title','aria-label','label']){
        if(!el.hasAttribute(attr))continue;
        const key='i18n'+attr.replaceAll('-',''),raw=el.dataset[key]||el.getAttribute(attr);el.dataset[key]=raw;
        el.setAttribute(attr,translate(raw));
      }
    }
    observer?.observe(document.body,{subtree:true,childList:true,characterData:true});
  }
  function setLanguage(lang){
    document.documentElement.lang=lang==='en'?'en':'ja';
    try{localStorage.setItem('parkingAdminLanguage',document.documentElement.lang);}catch{}
    document.getElementById('language-button').textContent=english()?'日本語':'EN';
    render();apply();
  }
  document.addEventListener('DOMContentLoaded',()=>{
    observer=new MutationObserver(apply);
    document.getElementById('language-button').addEventListener('click',()=>setLanguage(english()?'ja':'en'));
    let lang='ja';try{lang=localStorage.getItem('parkingAdminLanguage')||'ja';}catch{}
    setLanguage(lang);
  });
  return {translate,apply,setLanguage};
})();
