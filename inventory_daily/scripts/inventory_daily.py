"""成品库存日报生成工具（精简版）"""
import os, datetime, sys

# 版本信息
__version__ = "1.0.2"
__version_date__ = "2026-09-07"

# 修复 Windows GBK 终端输出 Unicode emoji 的问题
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 说明：Excel COM 必须用 DispatchEx（独立实例），见 run() 中的注释

import win32com.client


def get_cell_value(cell):
    """安全读取单元格值"""
    val = cell.Value
    if val is None:
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0


def generate_report(date_str, plan_qty, done, ratio_str, begin_stock,
                    con_qty, container_cnt, cur_stock):
    """生成格式化回复文本"""
    return (f'「截至{date_str}日，本月当前计划数量 {int(plan_qty):,} 台，\n'
            f'已完成下线 {int(done):,} 台，完成占比 {ratio_str}，\n'
            f'期初库存 {int(begin_stock):,} 台，装柜 {int(con_qty):,} 台（{int(container_cnt):,} 柜），\n'
            f'当前库存 {int(cur_stock):,} 台。」')


def run():
    """主流程：读取 Excel → 运行 VBA 宏 → 另存 + 输出报表"""

    # ─────────────── 配置 ──────────────
    SRC_FILE = r"E:\OneDrive\桌面\生产情况日报\成品库存.xlsx"
    ADDIN_FILE = r"E:/SKILLS/inventory_daily/data/代码库.xlam"

    print("=" * 50)
    print("inventory_daily.py -- 成品库存日报生成工具")
    print(f"   版本：v{__version__} ({__version_date__})")
    print(f"   日期：{datetime.date.today()}\n")

    excel = None
    wb = None
    addin_wb = None

    try:
        # ─ Step 1: 打开 Excel，运行 VBA 宏 ─────────────
        print("[Step 1] 打开成品库存.xlsx，执行 VBA 宏...")
        # 使用 DispatchEx 创建"独立"Excel 实例，绝不附加/复用用户正在运行的
        # Excel（Dispatch/EnsureDispatch 会 attach 到已有实例并可能隐藏窗口、
        # 关闭用户的工作簿）。
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        print(f"   [1a] 检查加载项：{os.path.basename(ADDIN_FILE)} ...")
        if not os.path.exists(ADDIN_FILE):
            print(f"   [SKIP] 加载项未找到，跳过：{ADDIN_FILE}")
            addin_wb = None
        else:
            try:
                print(f"   [1a] 打开加载项：{os.path.basename(ADDIN_FILE)} ...")
                addin_wb = excel.Workbooks.Open(ADDIN_FILE)
            except Exception as e:
                print(f"   [WARN] 加载项打开失败，跳过：{e}")
                addin_wb = None

        print(f"   [1b] 打开主文件：{os.path.basename(SRC_FILE)} ...")
        wb = excel.Workbooks.Open(SRC_FILE)

        print(f"   [1c] 尝试启用宏安全设置...")
        # 尝试启用宏（如果未启用会失败）
        try:
            excel.SecurityLevel = 0  # 0 = 禁用宏保护，允许所有宏
            print(f"   [OK] 宏已启用")
        except Exception as e:
            print(f"   [WARN] 无法启用宏：{e}")
        
        print(f"   [1d] 执行宏：产量出货更新 ...")
        try:
            excel.Application.Run("产量出货更新")
            print(f"   [OK] VBA 宏执行成功")
        except Exception as e:
            print(f"   [WARN] 宏运行失败（可能已禁用）：{e}")
            # 即使宏失败，仍继续读取数据

        print(f"   [1d] 刷新透视表 (RefreshAll) ...")
        wb.RefreshAll()
        excel.CalculateUntilAsyncQueriesDone()
        print(f"   [OK] VBA 宏执行完成，透视表已刷新\n")

        # ─ Step 2: 读取"汇总" Sheet 数据 ──────────────
        print("[Step 2] 读取'汇总' Sheet 数据...")
        try:
            summary_sheet = wb.Sheets("汇总")
        except Exception:
            summary_sheet = wb.Sheets(1)

        # 数据位于"汇总" Sheet 第 22~24 行的合计单元格（沿用旧版坐标）
        plan_qty      = get_cell_value(summary_sheet.Range("E22"))   # 本月计划
        done          = get_cell_value(summary_sheet.Range("F22"))   # 已完成下线
        begin_stock   = get_cell_value(summary_sheet.Range("B23"))   # 期初库存
        con_qty       = get_cell_value(summary_sheet.Range("B24"))   # 装柜数量（台）
        container_cnt = get_cell_value(summary_sheet.Range("C24"))   # 装柜数（柜）
        cur_stock     = get_cell_value(summary_sheet.Range("C22"))   # 当前库存

        raw_ratio = summary_sheet.Range("F23").Value
        ratio = float(raw_ratio) if raw_ratio is not None else 0

        print(f"   本月计划={plan_qty} | 已完成下线={done} | 完成占比={ratio:.1%}")
        print(f"   期初库存={begin_stock} | 装柜={con_qty}台({container_cnt}柜) | 当前库存={cur_stock}\n")

        # ─ Step 3: 另存为新文件（防冲突）──────────────
        print("[Step 3] 另存为新文件...")
        today = datetime.date.today()
        dst_dir = os.path.dirname(SRC_FILE)
        dst_path = os.path.join(dst_dir, f"成品库存{today}.xlsx")

        if os.path.exists(dst_path):
            base_name = os.path.splitext(os.path.basename(dst_path))[0]
            for n in range(1, 99):
                candidate = os.path.join(dst_dir, f"{base_name}_{n}.xlsx")
                if not os.path.exists(candidate):
                    dst_path = candidate
                    break

        wb.SaveAs(dst_path, FileFormat=51)  # xlOpenXMLWorkbook (.xlsx)
        print(f"   [OK] 已保存：{dst_path}\n")

        # ─ Step 4: 输出格式化报告 ────────────────────
        ratio_str = f"{ratio:.1%}" if ratio else "N/A"
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        report_txt = generate_report(yesterday, plan_qty, done, ratio_str,
                                     begin_stock, con_qty, container_cnt, cur_stock)
        print(report_txt)

    except Exception as e:
        print(f"\n[FAIL] {e}")
        raise
    finally:
        if wb is not None:
            try:
                wb.Close(SaveChanges=False)
            except:
                pass
        if addin_wb is not None:
            try:
                addin_wb.Close(SaveChanges=False)
            except:
                pass
        if excel is not None:
            try:
                excel.Quit()
            except:
                pass


if __name__ == "__main__":
    run()
