#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
受控下载 MediaPipe Tasks PoseLandmarker 模型资产
并进行 SHA-256 哈希校验
"""

import sys
import hashlib
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "models"

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
MODEL_FILENAME = "pose_landmarker_full.task"
EXPECTED_SHA256 = "c1851e3914a84949ad4cb96e9fa22a452efeb38d2f50c05f01311ff0567e9f3b"


def download_and_verify():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = MODELS_DIR / MODEL_FILENAME

    print(f"[*] 目标路径: {target_path}")
    print(f"[*] 来源 URL: {MODEL_URL}")

    if target_path.exists():
        print("[*] 模型文件已存在，正在校验 SHA-256...")
        h = hashlib.sha256()
        with open(target_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        actual_sha256 = h.hexdigest()
        print(f"[*] 当前 SHA-256: {actual_sha256}")
        if actual_sha256.lower() == EXPECTED_SHA256.lower():
            print("[+] 模型哈希校验通过！")
            return 0
        else:
            print("[!] 哈希不匹配，准备重新下载...")

    print("[*] 开始下载模型...")
    try:
        urllib.request.urlretrieve(MODEL_URL, target_path)
        print("[+] 下载完成，正在进行 SHA-256 校验...")
        h = hashlib.sha256()
        with open(target_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        actual_sha256 = h.hexdigest()
        print(f"[*] 计算得到 SHA-256: {actual_sha256}")
        if actual_sha256.lower() == EXPECTED_SHA256.lower():
            print("[+] 模型哈希与契约完全吻合！")
            return 0
        else:
            print(f"[!] 警告: 计算哈希 ({actual_sha256}) 与预设期望 ({EXPECTED_SHA256}) 不匹配。")
            return 1
    except Exception as e:
        print(f"[-] 下载失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(download_and_verify())
