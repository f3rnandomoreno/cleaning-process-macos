import tkinter as tk
from tkinter import ttk, messagebox
import psutil
import signal
import os
import threading
import time

# A basic (and non‑exhaustive) list of essential macOS processes that should not
# be terminated.  You can expand this list to suit your workflow.
ESSENTIAL_NAMES = {
    "kernel_task",
    "launchd",
    "WindowServer",
    "hidd",
    "distnoted",
    "powerd",
    "loginwindow",
    "systemstats",
    "notifyd",
    "syslogd",
    "mdworker",
    "mds",
    "mds_stores",
    "bluetoothd",
    "configd",
}

ESSENTIAL_PIDS = {0, 1}  # kernel_task (0) and launchd (1)

REFRESH_INTERVAL = 3  # seconds

class ProcessManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cleaning Process MacOs") # Changed title here
        self.geometry("760x560")
        self.resizable(False, False)

        self._build_widgets()
        self._populate_tree()

        # Start a background thread to refresh periodically
        self.stop_refresh = threading.Event()
        threading.Thread(target=self._refresh_loop, daemon=True).start()

    # ---------------------------- GUI construction ---------------------------
    def _build_widgets(self):
        header = tk.Label(
            self,
            text="Processes on MacOS", # Changed text here
            font=("Helvetica", 16, "bold"),
            pady=5, # Reduced padding
        )
        header.pack()

        # Frame for RAM info
        ram_frame = tk.Frame(self)
        ram_frame.pack(pady=(0, 5))

        self.used_ram_label = tk.Label(
            ram_frame,
            text="Used RAM: ... GB",
            font=("Helvetica", 12),
        )
        self.used_ram_label.pack(side=tk.LEFT, padx=10)

        self.available_ram_label = tk.Label(
            ram_frame,
            text="Available RAM: ... GB",
            font=("Helvetica", 12),
        )
        self.available_ram_label.pack(side=tk.LEFT, padx=10)

        self.total_ram_label = tk.Label(
            ram_frame,
            text="Total RAM: ... GB",
            font=("Helvetica", 12),
        )
        self.total_ram_label.pack(side=tk.LEFT, padx=10)

        # Create a Treeview with columns
        columns = ("pid", "name", "mem")
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=20,
            selectmode="browse",
        )
        self.tree.heading("pid", text="PID")
        self.tree.heading("name", text="Process")
        self.tree.heading("mem", text="RAM (MB)")

        self.tree.column("pid", width=80, anchor="center")
        self.tree.column("name", width=400, anchor="w")
        self.tree.column("mem", width=120, anchor="e")

        # Style tags for color‑coding rows
        self.tree.tag_configure("essential", foreground="red")
        self.tree.tag_configure("nonessential", foreground="green")

        self.tree.pack(padx=10, pady=10, fill="both", expand=False)

        # Buttons frame
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)

        terminate_btn = tk.Button(
            btn_frame,
            text="Terminate Selected",
            command=self._terminate_selected,
            width=20,
        )
        terminate_btn.grid(row=0, column=0, padx=10)

        clean_btn = tk.Button(
            btn_frame,
            text="Clean All Non‑Essential",
            command=self._clean_nonessential,
            width=20,
        )
        clean_btn.grid(row=0, column=1, padx=10)

        refresh_btn = tk.Button(
            btn_frame,
            text="Refresh Now",
            command=self._populate_tree,
            width=15,
        )
        refresh_btn.grid(row=0, column=2, padx=10)

    # ---------------------------- Data functions ----------------------------
    def _refresh_loop(self):
        while not self.stop_refresh.is_set():
            time.sleep(REFRESH_INTERVAL)
            self._populate_tree()

    def _populate_tree(self):
        """Refresh the process list and system RAM info, preserving selection, sort order, and scroll position."""
        # --- Store current state ---
        selected_pid = None
        sel = self.tree.selection()
        if sel:
            try:
                selected_pid = int(self.tree.set(sel[0], "pid"))
            except ValueError:
                pass

        # Store current scroll position (top fraction)
        scroll_pos = self.tree.yview()[0]

        # --- Update System RAM Info ---
        try:
            mem_info = psutil.virtual_memory()
            total_gb = mem_info.total / (1024**3)
            available_gb = mem_info.available / (1024**3)
            used_gb = mem_info.used / (1024**3)
            self.used_ram_label.config(text=f"Used RAM: {used_gb:.2f} GB")
            self.available_ram_label.config(text=f"Available RAM: {available_gb:.2f} GB")
            self.total_ram_label.config(text=f"Total RAM: {total_gb:.2f} GB")
        except Exception as e:
            print(f"Error getting memory info: {e}") # Log error if needed
            self.used_ram_label.config(text="Used RAM: Error")
            self.available_ram_label.config(text="Available RAM: Error")
            self.total_ram_label.config(text="Total RAM: Error")

        # --- Incremental update of Treeview to preserve scroll and optimize performance ---
        # Gather process data first
        processes_data = []
        for proc in psutil.process_iter(attrs=["pid", "name", "memory_info"]):
            try:
                pid = proc.info["pid"]
                name = proc.info["name"] or "?"
                mem_info = proc.info["memory_info"]
                rss_mb = mem_info.rss / (1024 * 1024) if mem_info else 0.0
                is_essential = self._is_essential(pid, name)
                processes_data.append((pid, name, rss_mb, is_essential))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by memory usage (descending)
        processes_data.sort(key=lambda x: x[2], reverse=True)

        # Map existing items by PID
        existing = {int(self.tree.set(item, "pid")): item for item in self.tree.get_children()}
        new_items = {}

        for index, (pid, name, rss_mb, is_essential) in enumerate(processes_data):
            tag = "essential" if is_essential else "nonessential"
            if pid in existing:
                item_id = existing[pid]
                # Update values and tag
                self.tree.item(item_id, values=(pid, name, f"{rss_mb:.1f}"), tags=(tag,))
            else:
                # Insert new item at correct position
                item_id = self.tree.insert("", index, values=(pid, name, f"{rss_mb:.1f}"), tags=(tag,))
            # Reorder item to match sorted index
            self.tree.move(item_id, "", index)
            new_items[pid] = item_id

        # Remove items no longer present
        for pid, item_id in existing.items():
            if pid not in new_items:
                self.tree.delete(item_id)

        # Restore selection
        if selected_pid in new_items:
            self.tree.selection_set(new_items[selected_pid])

    @staticmethod
    def _is_essential(pid: int, name: str) -> bool:
        return pid in ESSENTIAL_PIDS or name in ESSENTIAL_NAMES

    # ---------------------------- Actions -----------------------------------
    def _terminate_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Please select a process first.")
            return
        pid = int(self.tree.set(sel[0], "pid"))
        name = self.tree.set(sel[0], "name")
        if self._is_essential(pid, name):
            messagebox.showwarning(
                "Essential process",
                f"{name} (PID {pid}) is essential and cannot be terminated.",
            )
            return
        self._send_sigterm(pid, name)

    def _clean_nonessential(self):
        count = 0
        for item in self.tree.get_children():
            pid = int(self.tree.set(item, "pid"))
            name = self.tree.set(item, "name")
            if not self._is_essential(pid, name):
                if self._send_sigterm(pid, name):
                    count += 1
        messagebox.showinfo("Cleanup", f"Sent terminate signal to {count} processes.")

    def _send_sigterm(self, pid: int, name: str) -> bool:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except PermissionError:
            messagebox.showerror(
                "Permission denied",
                f"No permission to terminate {name} (PID {pid}). Try running as sudo.",
            )
        except ProcessLookupError:
            # Process already gone
            pass
        return False

    # ---------------------------- Cleanup -----------------------------------
    def on_closing(self):
        self.stop_refresh.set()
        self.destroy()


def main():
    if os.geteuid() != 0:
        print("⚠️ Running without root privileges. You may not be able to terminate some processes.")
    app = ProcessManagerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
