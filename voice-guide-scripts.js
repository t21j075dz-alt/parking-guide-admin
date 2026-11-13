"use strict";
/**
 * 音声ガイダンス37種類。短く丁寧なナビ表現へ統一し、駐車枠は必ず2回案内。
 * 固定文・施設名・店舗名・エリア／区画番号を独立した音声部品に分割する。
 *
 * 事前保存するのは音声部品。再生時に同一の部品を組み合わせるため、
 * 施設や区画を変更しても固定文を再生成する必要はない。
 */
window.ParkingVoiceGuideScripts = (() => {
  const TEMPLATES = Object.freeze({
    // 01 条件入力後
    start_complex:
      "［目的施設名］内の［目的店舗名］への駐車案内を設定しました。［目的施設名］に近づくと、空き枠を自動で探します。現在の駐車場は［混雑状況］。運転中の操作はお控えください。",
    start_single:
      "［目的店舗名］への駐車案内を設定しました。目的地に近づくと、空き枠を自動で探します。現在の駐車場は［混雑状況］。運転中の操作はお控えください。",
    approaching: "まもなく目的地です。駐車場の空き状況を確認しています。",
    // 02 目的地接近後: 同じ駐車枠を必ず二度読む
    space_found:
      "まもなく目的地です。空き枠が見つかりました。ご案内する駐車枠は、［駐車枠］番です。繰り返します。［駐車枠］番です。場内は徐行し、現地の標識や係員の案内を優先してください。利用できない場合は、安全な場所に停車してから「再探索」を押してください。",
    space_alternative:
      "ご希望の条件に合う空き枠がないため、別の枠をご案内します。ご案内する駐車枠は、［駐車枠］番です。繰り返します。［駐車枠］番です。場内は徐行し、現地の標識や係員の案内を優先してください。",
    space_none:
      "現在、ご案内できる空き枠がありません。公道での空き待ちはお控えください。駐車場案内を終了します。ご利用ありがとうございました。",
    space_maybe_taken:
      "ご案内した駐車枠が埋まった可能性があります。安全な場所に停車してから「再探索」を押してください。",
    // 03 再探索
    retry_started: "空き枠をもう一度探しています。少々お待ちください。",
    retry_found:
      "新しい空き枠が見つかりました。ご案内する駐車枠は、［駐車枠］番です。繰り返します。［駐車枠］番です。現地の標識や係員の案内を優先してください。",
    retry_none:
      "申し訳ありません。現在、ご案内できる空き枠がありません。現地の案内表示をご確認ください。",
    // 04 停車・完了・終了
    arrival_detected:
      "ご案内した駐車枠に車を検知しました。ご自身の車ですか？安全に停車してから、画面の「はい」か「いいえ」を選んでください。",
    // 録画用の確認ボタンは「録画の駐車結果を確認」。音声では実験・録画の前置きを付けない。
    arrival_video_confirm:
      "ご案内した駐車枠に車を検知しました。安全に停車してから画面をご確認ください。",
    parking_completed: "駐車が完了しました。お疲れさまでした。お忘れ物にご注意ください。",
    guidance_ended: "駐車場案内を終了しました。ご利用ありがとうございました。",
    // 05 営業・施設・条件
    full: "現在、駐車場は満車です。空き枠が確認できるまで、ご案内できません。",
    rest: "本日、［施設名］は休業日です。営業日をご確認ください。",
    closed: "現在、［施設名］は営業時間外です。次の開店は［時刻］です。",
    closed_unknown: "現在、［施設名］は営業時間外です。営業時間をご確認ください。",
    space_changed: "ご案内する駐車枠が変わりました。新しい駐車枠をご案内します。",
    conditions_changed: "駐車条件を変更しました。新しい条件で空き枠を探します。",
    conditions_unavailable: "ご希望の条件に合う空き枠がありません。別の条件で探します。",
    destination_changed: "案内先を［駐車場名］に変更しました。",
    // 06 カメラ・位置情報・通信
    camera_disconnected:
      "カメラとの接続が切れました。最新の空き状況を確認できません。現地の案内表示をご確認ください。",
    camera_recovered: "カメラとの接続が回復しました。空き状況を更新しています。",
    recognition_unknown: "現在、駐車枠の空き状況を確認できません。現地の案内表示をご確認ください。",
    location_unknown:
      "現在地を取得できません。安全な場所に停車してから、位置情報の設定をご確認ください。",
    status_stale:
      "駐車場情報の更新が止まっています。表示中の空き状況は最新ではない可能性があります。現地の案内表示をご確認ください。",
    // 07 現在のアプリに未実装の検出は勝手に発火させない
    entrance_near: "まもなく駐車場入口です。入口の案内表示をご確認ください。",
    entrance_entered: "駐車場に入りました。歩行者に注意して、徐行してください。",
    route_turn: "この先を［方向］に進み、［エリア名］へお進みください。",
    space_unavailable: "ご案内した駐車枠は利用できません。別の駐車枠を探します。",
    timer_started: "駐車時間の記録を開始しました。",
    timer_elapsed: "現在の駐車時間は［駐車時間］です。",
    parked_location: "駐車した場所は、［駐車枠］番です。繰り返します。［駐車枠］番です。",
    exit_detected: "駐車場からの退出を確認しました。ご利用ありがとうございました。",
    // 現行アプリの研究用録画を実際の空きと誤認させない
    recorded_demo: "これは過去の録画映像を使った案内です。現在の空き状況ではありません。",
    voice_test_notice: "これは音声案内のテストです。駐車枠の情報は模擬データです。",
    // 固定文として事前生成しておくその他の既存案内
    closing_soon: "閉店まで1時間以内です。ご利用時間にご注意ください。",
  });

  const ENGLISH_TEMPLATES = Object.freeze({
  "start_complex": "Parking guidance is set for ［目的店舗名］ at ［目的施設名］. We will check for a space as you approach ［目的施設名］. Current status: ［混雑状況］. Do not operate your device while driving.",
  "start_single": "Parking guidance is set for ［目的店舗名］. We will check for a space as you approach. Current status: ［混雑状況］. Do not operate your device while driving.",
  "approaching": "You are approaching your destination. Checking parking availability.",
  "space_found": "A parking space is available. Your assigned space is ［駐車枠］. I repeat, ［駐車枠］. Drive slowly and follow on-site signs and staff instructions. If the space cannot be used, stop safely before searching again.",
  "space_alternative": "Your preferred space type is unavailable. We have assigned space ［駐車枠］. I repeat, ［駐車枠］. Drive slowly and follow on-site signs and staff instructions.",
  "space_none": "No parking space is available for guidance right now. Do not wait on public roads. Parking guidance will end. Thank you.",
  "space_maybe_taken": "Your assigned parking space may now be occupied. Stop in a safe place before searching again.",
  "retry_started": "Searching for an available parking space again. Please wait.",
  "retry_found": "A new parking space is available. Your assigned space is ［駐車枠］. I repeat, ［駐車枠］. Follow on-site signs and staff instructions.",
  "retry_none": "Sorry, no parking space is available for guidance. Check the on-site signs.",
  "arrival_detected": "A vehicle has been detected in your assigned space. Is it your vehicle? Stop safely before selecting Yes or No.",
  "arrival_video_confirm": "A vehicle has been detected in your assigned space. Stop safely and check the screen.",
  "parking_completed": "Parking is complete. Please check that you have all your belongings.",
  "guidance_ended": "Parking guidance has ended. Thank you for using the service.",
  "full": "The parking lot is full. Guidance is unavailable until a free space is confirmed.",
  "rest": "［施設名］ is closed today. Please check its opening days.",
  "closed": "［施設名］ is currently closed. The next opening is at ［時刻］.",
  "closed_unknown": "［施設名］ is currently closed. Please check its opening hours.",
  "space_changed": "Your assigned parking space has changed. We will guide you to the new space.",
  "conditions_changed": "Your parking preferences have changed. Searching again with the new preferences.",
  "conditions_unavailable": "No available space matches your preferences. Searching with alternative preferences.",
  "destination_changed": "Your destination has been changed to ［駐車場名］.",
  "camera_disconnected": "The camera connection has been lost. Current space availability cannot be confirmed. Follow on-site signs.",
  "camera_recovered": "The camera connection has been restored. Updating parking availability.",
  "recognition_unknown": "Parking availability cannot be confirmed at this time. Follow on-site signs.",
  "location_unknown": "Your location is unavailable. Stop safely before checking location settings.",
  "status_stale": "Parking information is no longer up to date. Follow on-site signs.",
  "entrance_near": "You are approaching the parking entrance. Check the entrance signs.",
  "entrance_entered": "You have entered the parking lot. Watch for pedestrians and drive slowly.",
  "route_turn": "Continue ［方向］ toward ［エリア名］.",
  "space_unavailable": "Your assigned space is no longer available. Searching for another space.",
  "timer_started": "Parking time tracking has started.",
  "timer_elapsed": "Your current parking time is ［駐車時間］.",
  "parked_location": "Your parked location is space ［駐車枠］. I repeat, ［駐車枠］.",
  "exit_detected": "You have left the parking lot. Thank you for using the service.",
  "recorded_demo": "This guidance uses an earlier video recording. It does not show live availability.",
  "voice_test_notice": "This is a voice guidance test using simulated parking information.",
  "closing_soon": "The facility will close within one hour. Please plan your visit accordingly."
});

  // 句点で切り、残りはプレースホルダー単位に分解。
  // 読み上げの間が不自然にならないように、短い句をまとめる。
  function build(id, values = {}, locale = "ja-JP") {
    const english = /^en(?:-|$)/i.test(locale);
    const template = (english ? ENGLISH_TEMPLATES : TEMPLATES)[id];
    if (!template) throw new Error("Unknown voice script: " + id);
    const parts = [];
    const pieces = template.split(/(［[^］]+］)/g).filter(Boolean);
    for (const piece of pieces) {
      const placeholder = /^［([^］]+)］$/.exec(piece);
      if (placeholder) {
        const value = String(values[placeholder[1]] ?? "").trim();
        if (!value) throw new Error("Voice value missing: " + placeholder[1]);
        parts.push({ role: placeholder[1], text: value });
      } else {
        const phrases = piece.match(english ? /[^.!?]+[.!?]?|[.!?]+/g : /[^。！？]+[。！？]?/g) || [];
        for (const phrase of phrases)
          if (phrase.trim()) parts.push({ role: "fixed", text: phrase });
      }
    }
    return {
      id,
      parts,
      text: parts.map((p) => p.text).join(""),
    };
  }

  function catalogFixed() {
    // 施設の選択前でも静的文言だけ先に音声ファイルとして保存できる。
    const fixed = new Set();
    for (const id of Object.keys(TEMPLATES)) {
      const template = TEMPLATES[id];
      for (const piece of template.split(/［[^］]+］/g)) {
        for (const fragment of piece.match(/[^。！？]+[。！？]?/g) || []) {
          if (fragment.trim()) fixed.add(fragment);
        }
      }
    }
    return [...fixed];
  }

  return Object.freeze({ build, catalogFixed, ids: Object.freeze(Object.keys(TEMPLATES)) });
})();
