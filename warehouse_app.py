"""Warehouse Check desktop entry point (Python and portable Windows builds)."""
import sys
import tkinter as tk
from tkinter import messagebox
from warehouse.ui import Application


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--verify-package':
        from warehouse.package_check import verify_package
        return verify_package(sys.argv[2])
    root = tk.Tk()
    try:
        Application(root)
    except Exception as exc:
        root.withdraw()
        messagebox.showerror("Warehouse Check", f"Aplikasi gagal dibuka:\n{exc}", parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
