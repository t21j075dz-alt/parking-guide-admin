#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管理マップから日光の録画へ投影した画角内の区画だけを安全に取込む。

デフォルトは検査だけ。--apply 時には元動画の先頭/中間/末尾に
各区画を重ねて人が確認する。実カメラやクラウドには触れない。
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import json
from math import isfinite
import os
from pathlib import Path
import shutil
import tempfile

from nikko_video_config import (
    CAMERA_ID, FACILITY_ID, MAX_VISIBLE_SPACES, checked_config, make_config,
    read_settings, record_video_calibration,
)
from zone_geometry import normalize_corners, audit_zones


def checked_projection(alignment):
    if not isinstance(alignment, dict) or alignment.get("schema_version") != 1:
        raise ValueError("位置合わせJSONの形式が不正です")
    if alignment.get("facility_id") != FACILITY_ID or alignment.get("camera_id") != CAMERA_ID:
        raise ValueError("道の駅日光の録画専用施設・カメラIDを指定してください")
    ids, zones = alignment.get("space_uids"), alignment.get("space_zones")
    excluded = alignment.get("excluded_space_uids", [])
    if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_VISIBLE_SPACES
            or any(not isinstance(uid, str) for uid in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("画角内の区画IDが不正です")
    from nikko_video_config import UID_PATTERN
    if not all(UID_PATTERN.fullmatch(uid) for uid in ids):
        raise ValueError("区画IDはspace_で始めてください")
    if (not isinstance(zones, dict) or set(zones) != set(ids)
            or not isinstance(excluded, list)
            or len(set(excluded)) != len(excluded)
            or set(ids) & set(excluded)
            or not all(isinstance(uid, str) and UID_PATTERN.fullmatch(uid) for uid in excluded)):
        raise ValueError("画角内と対象外の区画IDが重複・不一致です")
    dimensions = alignment.get("image_width"), alignment.get("image_height")
    if any(type(d) is not int or d <= 0 for d in dimensions):
        raise ValueError("録画画像の解像度が正しくありません")
    method = alignment.get("alignment_method", "global-homography")
    if method not in ("global-homography", "hybrid-zones", "manual-zones"):
        raise ValueError("位置合わせ方法が不正です")
    map_points = alignment.get("map_points")
    image_points = alignment.get("image_points")
    manual_only = method == "manual-zones"
    if (not isinstance(map_points, list) or not isinstance(image_points, list)
            or len(map_points) != len(image_points)
            or (manual_only and len(map_points) != 0)
            or (not manual_only and not 4 <= len(map_points) <= 24)):
        raise ValueError("全体の位置合わせは4～24組、写真からの直接登録は対応点0組で指定してください")
    manual_ids = alignment.get("manual_zone_uids", [])
    if (not isinstance(manual_ids, list) or len(manual_ids) != len(set(manual_ids))
            or not all(isinstance(uid, str) for uid in manual_ids)
            or not set(manual_ids).issubset(set(ids))
            or (manual_only and set(manual_ids) != set(ids))
            or (method == "global-homography" and manual_ids)):
        raise ValueError("写真上で手動登録した駐車枠IDが一致しません")
    for pairs in (map_points, image_points):
        for pair in pairs:
            if (not isinstance(pair, list) or len(pair) != 2 or
                    not all(type(n) in (int, float) and isfinite(n)
                            and 0 <= n <= 1 for n in pair)):
                raise ValueError("位置合わせ点の範囲が不正です")
    # 既存の4点JSONは互換。新しい多点JSONの診断結果も保存前に検査。
    quality = alignment.get("alignment_quality")
    if manual_only and quality is not None:
        raise ValueError("写真から直接登録した枠には全体変換の精度診断を付けないでください")
    if quality is not None:
        outliers = quality.get("outlier_indices") if isinstance(quality, dict) else None
        valid_outliers = (isinstance(outliers, list)
                          and all(type(i) is int and 0 <= i < len(map_points)
                                  for i in outliers)
                          and len(outliers) == len(set(outliers)))
        if (not isinstance(quality, dict)
                or quality.get("method") not in ("four-point", "ransac-least-squares")
                or type(quality.get("point_count")) is not int
                or quality["point_count"] != len(map_points)
                or type(quality.get("inlier_count")) is not int
                or not 4 <= quality["inlier_count"] <= len(map_points)
                or not valid_outliers
                or quality["inlier_count"] + len(outliers) != len(map_points)
                or (outliers and (method != "hybrid-zones" or not manual_ids))
                or type(quality.get("rms_pixels")) not in (int, float)
                or not isfinite(quality["rms_pixels"])
                or quality["rms_pixels"] < 0):
            raise ValueError("位置合わせの精度診断が不正です。外れ点と区画の補正結果を確認してください")
    checked = {}
    for uid in ids:
        try:
            checked[uid] = normalize_corners(zones[uid])
        except (ValueError, TypeError) as exc:
            raise ValueError(uid + " の位置が不正です: " + str(exc)) from exc
    problems = audit_zones(checked)
    if any("重なって" in issue for issue in problems):
        raise ValueError("映像内の区画が重複しています: " + "; ".join(problems))
    return checked, excluded, dimensions, problems


def video_info(video):
    import cv2
    from video_replay import validate_video
    source = cv2.VideoCapture(str(validate_video(video)))
    try:
        if not source.isOpened():
            raise ValueError("録画を開けません")
        count=int(source.get(cv2.CAP_PROP_FRAME_COUNT))
        ok,frame=source.read()
        if not ok or frame is None:
            raise ValueError("動画の最初の映像が読み取れません")
        height,width=frame.shape[:2]
        return width,height,count
    finally:
        source.release()


def verify_samples(video, zones, dimensions):
    import cv2
    from monitor import overlay
    from video_demo_support import draw_demo_watermark
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError("録画を開けません")
    try:
        count=max(1,int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        fps=max(1.0,float(cap.get(cv2.CAP_PROP_FPS)))
        frames=sorted(set([0,max(0,count//2),max(0,count-1)]))
        print(f"【画角の目視確認】{len(zones)}区画／先頭・中間・末尾の映像を表示します。")
        print("各場面で、対象の区画が映っているか確認。S=正しい / Q=中止")
        for index in frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES,index)
            ok,frame=cap.read()
            if not ok or frame is None:
                raise ValueError("確認用の映像が読み取れません")
            if tuple(frame.shape[1::-1])!=tuple(dimensions):
                raise ValueError("録画の途中で画像サイズが変わりました")
            view=overlay(frame,zones,{uid:"unknown" for uid in zones},[],[])
            view=draw_demo_watermark(view,cv2,index/fps)
            window=f"Nikko recorded video / frame {index+1}/{count} / S approve Q cancel"
            cv2.namedWindow(window,cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window,1280,800)
            try:
                while True:
                    cv2.imshow(window,view)
                    key=cv2.waitKey(50)&0xFF
                    if key in (ord("s"),ord("S")):break
                    if key in (ord("q"),ord("Q"),27):
                        raise ValueError("位置が一致しないため取込みを中止しました")
            finally:
                cv2.destroyWindow(window)
        return True
    finally:
        cap.release()


def proposed_config(existing, alignment, zones, video, dimensions):
    updated=deepcopy(existing)
    updated["space_uids"]=list(alignment["space_uids"])
    updated["space_zones"]=zones
    updated["excluded_space_uids"]=list(alignment.get("excluded_space_uids",[]))
    updated["entry_zone"]=[]
    updated["exit_zone"]=[]
    updated.pop("recorded_calibration",None)
    record_video_calibration(updated,video,*dimensions)
    return checked_config(updated)


def save_config(path, updated):
    path=Path(path).resolve()
    backup=None
    if path.is_file():
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup=path.with_name(path.stem+"_backup_"+stamp+".json")
        shutil.copy2(path,backup)
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,
                                     suffix=".json",delete=False) as stream:
        temporary=Path(stream.name)
        json.dump(updated,stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
    return backup


def main(argv=None):
    parser=argparse.ArgumentParser(description="日光・マップ投影から画角内の区画を録画設定へ反映")
    parser.add_argument("--alignment",required=True,help="管理者アプリから書き出した日光の位置合わせJSON")
    parser.add_argument("--video",required=True,help="実際に解析する録画")
    parser.add_argument("--config",default="config_nikko_video_demo.json")
    parser.add_argument("--base",default="config.json",help="既存の学習済みモデル・公開用接続設定")
    parser.add_argument("--apply",action="store_true",help="3場面の目視確認後だけ設定を保存")
    args=parser.parse_args(argv)
    alignment=read_settings(args.alignment)
    zones,excluded,dimensions,warnings=checked_projection(alignment)
    vw,vh,count=video_info(args.video)
    if abs((vw/vh)/(dimensions[0]/dimensions[1])-1)>.015:
        raise ValueError("位置合わせに使用した写真と元動画の縦横比が異なります")
    settings= (checked_config(read_settings(args.config)) if Path(args.config).is_file()
               else make_config(read_settings(args.base), alignment["space_uids"]))
    candidate=proposed_config(settings,alignment,zones,args.video,(vw,vh))
    print(f"【道の駅日光】録画に映る{len(zones)}区画を判定対象／対象外{len(excluded)}区画")
    if warnings:
        for warning in warnings:print("【区画の注意】"+warning)
    print("【元動画】"+str(Path(args.video).resolve()))
    print("【書込み先】"+str(Path(args.config).resolve()))
    print("【保護】他施設と実カメラの設定は変更しません。")
    if not args.apply:
        print("【確認のみ】ファイルは変更していません。--applyで画角の目視確認後に保存できます。")
        return 0
    verify_samples(args.video,zones,(vw,vh))
    backup=save_config(args.config,candidate)
    if backup:print("【バックアップ】"+str(backup))
    print("【保存】"+str(Path(args.config).resolve()))
    print("【監視対象】"+", ".join(zones))
    print("【注意】未登録・画角外の区画は現在の空きとして案内できません。")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
