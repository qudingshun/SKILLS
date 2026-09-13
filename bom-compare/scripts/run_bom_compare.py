import win32com.client
import os
import sys
import gc
import time

try:
    import pythoncom
except ImportError:  # pragma: no cover
    pythoncom = None

XLSM_PATH = r'E:\OneDrive\桌面\桌面临时文件\PMC小工具\BOM核对.xlsm'
MACRO_NAME = '核对BOM2'
SHEET_NAME = 'Sheet1 (2)'
FILTER_VALUE = '无差异'
FILTER_COLUMN_INDEX = 3  # 1-based column C


def _cleanup_excel(xl=None, wb=None, quit_excel=True):
    """ Robustly release Excel COM objects and quit only this instance. """
    try:
        if wb is not None:
            wb.Close(False)
    except Exception:
        pass
    try:
        if quit_excel and xl is not None:
            xl.Quit()
    except Exception:
        pass
    finally:
        # Release COM references before deletion
        for obj in (wb, xl):
            if obj is not None:
                try:
                    del obj
                except Exception:
                    pass
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
        gc.collect()


def _detect_excel_running():
    """Return True if an Excel instance is already running."""
    try:
        win32com.client.GetActiveObject('Excel.Application')
        return True
    except Exception:
        return False


def run_bom_compare(visible=False, timeout=300):
    """打开BOM核对.xlsm，运行核对BOM2宏，保存后读取Sheet1结果。"""
    if pythoncom is not None:
        pythoncom.CoInitialize()

    xl = None
    wb = None
    excel_already_running = _detect_excel_running()
    try:
        print('[打开] {}'.format(XLSM_PATH))
        if excel_already_running:
            xl = win32com.client.GetActiveObject('Excel.Application')
        else:
            xl = win32com.client.DispatchEx('Excel.Application')
        xl.Visible = visible
        xl.DisplayAlerts = False

        wb = xl.Workbooks.Open(XLSM_PATH)

        print('[运行宏] {}...'.format(MACRO_NAME))
        xl.Run(MACRO_NAME)

        print('[保存] 文件...')
        wb.Save()

        print('[读取] {}...'.format(SHEET_NAME))
        ws = wb.Sheets(SHEET_NAME)
        last_row = ws.Cells(ws.Rows.Count, 'A').End(-4162).Row  # xlUp = -4162

        headers = None
        results = []
        for r in range(1, last_row + 1):
            row = [ws.Cells(r, c).Value for c in range(1, 8)]
            if r == 1:
                headers = row
                continue
            # 过滤掉 C 列显示“无差异”的行，其余全部输出
            if len(row) >= FILTER_COLUMN_INDEX and row[FILTER_COLUMN_INDEX - 1] == FILTER_VALUE:
                continue
            results.append(row)

        return {
            'status': 'success',
            'headers': headers,
            'rows': results,
            'total': len(results)
        }

    except Exception as e:
        msg = str(e)
        if 'RPC server is unavailable' in msg or 'CoInitialize' in msg:
            msg = 'Excel COM 初始化失败，请确认 Excel 已安装且当前用户可正常启动。'
        elif '429' in msg:
            msg = '无法创建 Excel 实例（错误 429），可能是 32 位 Python 与 64 位 Excel 不兼容，或 Excel 未正确安装。'
        elif '0x800A03EC' in msg:
            msg = 'Excel 内部错误（0x800A03EC），文件可能正被占用或路径不可访问。'
        elif 'timeout' in msg.lower():
            msg = 'Excel 宏执行超时（{}秒），请检查宏是否卡死。'.format(timeout)
        return {'status': 'error', 'message': msg}
    finally:
        _cleanup_excel(xl=xl, wb=wb, quit_excel=not excel_already_running)


if __name__ == '__main__':
    visible = '--visible' in sys.argv
    result = run_bom_compare(visible=visible)

    print('\n=== RESULT ===')
    print('Status: {}'.format(result.get('status')))
    if result.get('status') == 'success':
        print('Total rows: {}'.format(result['total']))
        print('Headers: {}'.format(result['headers']))
        print()
        for i, row in enumerate(result['rows'][:20], 1):
            print('{:3}. {}'.format(i, row))
        if result['total'] > 20:
            print('... and {} more rows'.format(result['total'] - 20))
    else:
        print('Error: {}'.format(result.get('message')))
