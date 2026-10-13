"""
摄像头拍照工具 - 打开摄像头拍摄一张照片输出。
用法:
    py camera_capture.py
    py camera_capture.py --list
    py camera_capture.py --index 1 --delay 3 --mirror --format png
"""
import argparse
import os
import sys
import time

import cv2

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass

OUTPUT_DIR = r'E:\SKILLS\camera-capture\images'
MAX_PROBE = 10


def list_cameras():
    """扫描并返回可用摄像头索引及其分辨率"""
    found = []
    for i in range(MAX_PROBE):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            found.append((i, w, h))
        cap.release()
    return found


def open_camera(index, width, height):
    """优先用 DSHOW 后端打开摄像头，失败则回退默认后端"""
    for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            if width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            if height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap
        cap.release()
    return None


def is_valid(frame):
    """过滤摄像头冷启动/无信号时的纯色空帧"""
    if frame is None or frame.size == 0:
        return False
    return float(frame.std()) > 3.0


def grab_frame(cap, warmup, timeout=15.0):
    """持续读取直到拿到有效画面，兼容摄像头冷启动返回的空帧"""
    deadline = time.time() + max(warmup, 0) + timeout
    warm_until = time.time() + max(warmup, 0)
    best = None
    best_score = -1.0
    frames = 0
    while time.time() < deadline:
        ok, img = cap.read()
        if not ok or img is None:
            time.sleep(0.01)
            continue
        frames += 1
        score = float(img.std())
        if score > best_score:
            best, best_score = img, score
        if time.time() >= warm_until and is_valid(img):
            return img, frames
    if best is None:
        return None, frames
    print(f'WARN: 画面疑似空白帧 (std={best_score:.1f})，已使用最后一帧')
    return best, frames


def save_image(frame, fmt, mirror, index):
    """保存图片，返回文件路径"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if mirror:
        frame = cv2.flip(frame, 1)
    ext = 'png' if fmt == 'png' else 'jpg'
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    path = os.path.join(OUTPUT_DIR, f'camera_{timestamp}_{index}.{ext}')
    params = [cv2.IMWRITE_JPEG_QUALITY, 92] if ext == 'jpg' else [cv2.IMWRITE_PNG_COMPRESSION, 3]
    if not cv2.imwrite(path, frame, params):
        raise RuntimeError(f'图片写入失败: {path}')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description='摄像头拍照')
    parser.add_argument('--index', type=int, default=0, help='摄像头索引，默认 0')
    parser.add_argument('--delay', type=float, default=0, help='拍摄前等待秒数，用于倒计时')
    parser.add_argument('--warmup', type=float, default=1.5, help='曝光预热秒数，默认 1.5')
    parser.add_argument('--mirror', action='store_true', help='水平翻转（前置摄像头用）')
    parser.add_argument('--format', choices=['jpg', 'png'], default='jpg', help='图片格式，默认 jpg')
    parser.add_argument('--width', type=int, default=0, help='强制宽度')
    parser.add_argument('--height', type=int, default=0, help='强制高度')
    parser.add_argument('--list', action='store_true', help='列出可用摄像头后退出')
    args = parser.parse_args(argv)

    if args.list:
        cams = list_cameras()
        if not cams:
            print('未检测到可用摄像头')
            return 1
        for i, w, h in cams:
            print(f'摄像头 {i}: {w}x{h}')
        return 0

    cap = open_camera(args.index, args.width, args.height)
    if cap is None:
        cams = list_cameras()
        print(f'ERROR: 无法打开摄像头 {args.index}')
        if cams:
            print('可用摄像头: ' + ', '.join(str(c[0]) for c in cams))
        else:
            print('未检测到任何可用摄像头，请检查设备连接或系统隐私设置（允许桌面应用访问摄像头）')
        return 1

    try:
        if args.delay > 0:
            for i in range(int(args.delay), 0, -1):
                ret, _ = cap.read()
                print(f'{i} 秒后拍摄...')
                time.sleep(1)
            if not ret:
                return 1
        else:
            print('正在拍照...')
        frame, frames = grab_frame(cap, args.warmup)
        if frame is None:
            print('ERROR: 摄像头未返回画面')
            return 1
        path = save_image(frame, args.format, args.mirror, args.index)
    finally:
        cap.release()

    h, w = frame.shape[:2]
    print(f'拍照完成: {path}')
    print(f'   尺寸: {w}x{h}  有效读取帧数: {frames}')
    print(f'   文件大小: {os.path.getsize(path) / 1024:.1f} KB')
    print('[DELIVER] 把下面这行原样、单独一行写进最终回复,才能推送到微信。')
    print('[DELIVER] 禁止包在 ``` 代码块里, 禁止加行内反引号, 禁止加 > 或 >>> 前缀, 前面不要有任何字符。')
    print(f'MEDIA:{path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
