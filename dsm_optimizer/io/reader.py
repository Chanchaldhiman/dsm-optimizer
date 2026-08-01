import numpy as np
import openpyxl
import csv


def read_dsm(filepath, sheet=0):
    """Auto-detect file type and return (matrix, labels)."""
    if filepath.lower().endswith('.csv'):
        return _read_csv(filepath)
    return _read_excel(filepath, sheet)


def _read_csv(filepath):
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        reader = list(csv.reader(f))
    labels = [row[0] for row in reader[1:] if row]
    n = len(labels)
    matrix = np.zeros((n, n), dtype=float)
    for i, row in enumerate(reader[1:n + 1]):
        for j, val in enumerate(row[1:n + 1]):
            try:
                matrix[i, j] = float(val)
            except (ValueError, TypeError):
                pass
    np.fill_diagonal(matrix, 0)
    return matrix, labels


def _read_excel(filepath, sheet=0):
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[sheet]
    data = [list(row) for row in ws.values]
    wb.close()

    # Skip fully-empty leading rows
    start = 0
    for i, row in enumerate(data):
        if any(v is not None for v in row):
            start = i
            break

    # Extract labels from first column of data rows (skip header row)
    labels = []
    for row in data[start + 1:]:
        if not row or row[0] is None:
            continue
        raw = str(row[0]).strip()
        if not raw:
            continue
        # Strip leading index number if format is "1  Battery" or "1. Battery"
        import re
        cleaned = re.sub(r'^\d+[\.\s]+', '', raw).strip()
        labels.append(cleaned if cleaned else raw)

    n = len(labels)
    if n == 0:
        raise ValueError("No component labels found. Check sheet index and format.")

    matrix = np.zeros((n, n), dtype=float)
    for i, row in enumerate(data[start + 1: start + 1 + n]):
        cells = list(row)
        for j in range(n):
            idx = j + 1      # col 0 = label, col 1..n = matrix
            if idx >= len(cells):
                continue
            v = cells[idx]
            if v is None or v == '':
                continue
            sv = str(v).strip().upper()
            if sv in ('X', '✓', '1', 'YES'):
                matrix[i, j] = 1.0
            else:
                try:
                    matrix[i, j] = float(v)
                except (ValueError, TypeError):
                    pass

    np.fill_diagonal(matrix, 0)
    return matrix, labels
