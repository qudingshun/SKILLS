"""
屏幕截图工具 - 多屏合并
检测所有显示器，逐屏截图，合并为一张图片输出。
"""
import mss
from PIL import Image
import os
import time


def capture_all():
    """截图所有显示器并合并为一张图片"""
    with mss.MSS() as sct:
        monitors = sct.monitors

        # 第一个 monitor 是虚拟屏幕（包含所有显示器）
        virtual = monitors[0]
        v_width = virtual['width']
        v_height = virtual['height']

        print(f"虚拟屏幕大小: {v_width}x{v_height}")
        print(f"检测到 {len(monitors)-1} 个物理显示器")

        # 截取整个虚拟屏幕
        screenshot = sct.grab(virtual)
        img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)

        return img


def main():
    output_dir = r'E:\SKILLS\screen-capture\images'
    os.makedirs(output_dir, exist_ok=True)

    timestamp = time.strftime('%Y%m%d_%H%M%S')
    output_path = os.path.join(output_dir, f'screen_{timestamp}.png')

    print("正在截图...")
    img = capture_all()
    img.save(output_path)

    print(f"✅ 截图完成: {output_path}")
    print(f"   尺寸: {img.size[0]}x{img.size[1]}")
    print(f"   文件大小: {os.path.getsize(output_path) / 1024:.1f} KB")
    # 打印 MEDIA: 行供 Hermes 网关抓取
    print(f"MEDIA:{output_path}")
    
    return output_path


if __name__ == '__main__':
    main()
