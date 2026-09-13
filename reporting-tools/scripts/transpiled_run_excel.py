"""
转译版 — 跑回货工具

在后台（不可见）执行 Excel，完成：
1. 打开 回货工具.xlsm
2. 执行 model1.yijian 宏
3. 另存为带日期的 .xlsm
"""
import os, sys
from datetime import datetime
import win32com.client as win32
import pythoncom

SRC_DIR = r"E:\OneDrive\桌面\桌面临时文件\PMC小工具"
SRC_FILE = os.path.join(SRC_DIR, "回货工具.xlsm")


def build_dst():
    """生成目标文件名（格式：yy.m.d），冲突自动加序列号"""
    now = datetime.now()
    date_suffix = f"{now.year % 100}.{now.month}.{now.day}"
    dst = os.path.join(SRC_DIR, f"回货工具{date_suffix}.xlsm")
    if not os.path.exists(dst):
        return dst
    stem = dst.replace(".xlsm", "")
    for n in range(1, 100):
        candidate = f"{stem}({n}).xlsm"
        if not os.path.exists(candidate):
            return candidate
    return dst


def run_excel():
    print(f"\n{'='*55}")
    print(f"  【转译】跑回货工具  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}")

    if not os.path.exists(SRC_FILE):
        print(f"  [错误] 源文件不存在: {SRC_FILE}")
        return False

    dst = build_dst()

    excel = None
    wb = None
    try:
        try:
            excel = win32.GetActiveObject("Excel.Application")
            excel_was_running = True
            print("  [INFO] 检测到已运行的 Excel 实例，将复用不关闭")
        except:
            excel = win32.gencache.EnsureDispatch("Excel.Application")
            excel_was_running = False
        pythoncom.CoInitialize()
        excel.DisplayAlerts = False
        excel.Visible = False  # 后台运行，不打开 Excel 窗口

        print(f"  打开: {os.path.basename(SRC_FILE)}")
        wb = excel.Workbooks.Open(SRC_FILE)

        macro = "model1.yijian"
        print(f"  执行宏: {macro}")
        excel.Application.Run(macro)

        print(f"  另存为: {os.path.basename(dst)}")
        wb.SaveAs(dst, FileFormat=52)  # xlOpenXMLWorkbookMacroEnabled

        print(f"\n  [OK] 完成：{dst}")
        return True

    except Exception as e:
        print(f"  [错误] {e}")
        return False

    finally:
        if wb:
            try:
                wb.Close(SaveChanges=False)
                wb = None
            except:
                pass
        if not excel_was_running:
            if excel:
                try: excel.Quit()
                except: pass
            import gc
            gc.collect()
        else:
            print("  [INFO] Excel 先前已运行，跳过 Quit，避免关闭其他文件")
