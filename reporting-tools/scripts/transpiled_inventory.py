"""
转译版 — 产销存日报（三步流程）

1. 打开 成品库存.xlsx，加载 代码库.xlam 加载项
2. 执行"产量出货更新"宏（后台不可见）
3. 另存后读取"汇总"Sheet，输出格式化的产销存数据
"""
import os, sys, time
from datetime import date, datetime, timedelta
import win32com.client as win32
import pythoncom
import openpyxl

BASE_DIR = r"E:\OneDrive\桌面\生产情况日报"
SRC_FILE = os.path.join(BASE_DIR, "成品库存.xlsx")
ADDIN_FILE = r"E:\OneDrive\工作\9、VBA程序\回货引用文件\代码库\代码库.xlam"

CELL_MAP = {
    "plan":         "E22",
    "done":         "F22",
    "ratio":        "F23",
    "begin_stock":  "B23",
    "container_qty": "B24",
    "container_ct":  "C24",
    "cur_stock":    "C22",
}


def build_dst():
    """生成 成品库存yyyy-mm-dd.xlsx，已存在时自动加 (n) 序列号"""
    date_str = date.today().strftime("%Y-%m-%d")
    dst = os.path.join(BASE_DIR, f"成品库存{date_str}.xlsx")
    if not os.path.exists(dst):
        return dst
    stem = dst.replace(".xlsx", "")
    for n in range(1, 100):
        candidate = f"{stem} ({n}).xlsx"
        if not os.path.exists(candidate):
            return candidate
    return dst


def read_summary(filepath):
    """用 openpyxl 读取已保存文件的汇总数据"""
    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        if "汇总" not in wb.sheetnames:
            print(f"  [警告] 找不到'汇总'Sheet，可用: {wb.sheetnames}")
            wb.close()
            return None
        ws = wb["汇总"]
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

        def safe_int(cell):
            v = ws[cell].value
            return int(v) if v is not None else "?"

        plan         = safe_int("E22")
        done         = safe_int("F22")
        ratio_v      = ws["F23"].value
        ratio        = f"{int(float(ratio_v) * 100)}%" if ratio_v else "?"
        begin_stock  = safe_int("B23")
        cqty         = safe_int("B24")
        cct          = safe_int("C24")
        cur_stock    = safe_int("C22")

        result = (
            f"截至{yesterday}日，本月计划{plan}台，"
            f"已完成下线{done}台（{ratio}），"
            f"期初库存{begin_stock}台，"
            f"装柜{cqty}台（{cct}柜），"
            f"当前库存{cur_stock}台。"
        )
        wb.close()
        return result
    except Exception as e:
        print(f"  [警告] 读取汇总失败: {e}")
        return None


def run_inventory():
    print(f"\n{'='*55}")
    print(f"  【转译】产销存日报  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}")

    # 检查源文件
    errors = []
    if not os.path.exists(SRC_FILE):
        errors.append(f"成品库存.xlsx 不存在: {SRC_FILE}")
    if not os.path.exists(ADDIN_FILE):
        errors.append(f"代码库.xlam 不存在: {ADDIN_FILE}")
    if errors:
        for e in errors:
            print(f"  [错误] {e}")
        return False

    dst = build_dst()

    excel = None
    wb = None
    addin_wb = None
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

        print(f"  加载加载项: {os.path.basename(ADDIN_FILE)}")
        addin_wb = excel.Workbooks.Open(ADDIN_FILE)

        print(f"  打开: {os.path.basename(SRC_FILE)}")
        wb = excel.Workbooks.Open(SRC_FILE)

        macro = "产量出货更新"
        print(f"  执行宏: {macro}")
        excel.Application.Run(macro)

        print(f"  另存为: {os.path.basename(dst)}")
        wb.SaveAs(dst, FileFormat=51)  # xlOpenXMLWorkbook (.xlsx)
        wb.Close(SaveChanges=False)
        wb = None
        addin_wb.Close(SaveChanges=False)
        addin_wb = None

        time.sleep(1)

        # 读取汇总数据
        result = read_summary(dst)
        if result:
            print(f"\n  {result}")
            print(f"\n  [OK] 完成：{dst}")
            return True

        print(f"  [OK] 完成（无汇总数据）：{dst}")
        return True

    except Exception as e:
        print(f"  [错误] {e}")
        return False

    finally:
        if wb:
            try: wb.Close(SaveChanges=False)
            except: pass
        if addin_wb:
            try: addin_wb.Close(SaveChanges=False)
            except: pass
        if not excel_was_running:
            if excel:
                try: excel.Quit()
                except: pass
        else:
            print("  [INFO] Excel 先前已运行，跳过 Quit，避免关闭其他文件")


if __name__ == "__main__":
    run_inventory()
