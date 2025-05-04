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
        """Refresh the process list and system RAM info, preserving selection and sorting by memory."""
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

        # --- Populate Process List (existing logic) ---
        selected_pid = None
        sel = self.tree.selection()
        if sel:
            try:
                selected_pid = int(self.tree.set(sel[0], "pid"))
            except ValueError:
                pass

        # Clear current items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Gather process data first
        processes_data = []
        for proc in psutil.process_iter(attrs=["pid", "name", "memory_info"]):
            try:
                pid = proc.info["pid"]
                name = proc.info["name"] or "?"
                mem_info = proc.info["memory_info"]
                rss_mb = 0.0 # Default to 0 if no info
                if mem_info:
                    rss_bytes = mem_info.rss
                    rss_mb = rss_bytes / (1024 * 1024)

                is_essential = self._is_essential(pid, name)
                processes_data.append({
                    "pid": pid,
                    "name": name,
                    "rss_mb": rss_mb,
                    "is_essential": is_essential
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by memory usage (descending)
        processes_data.sort(key=lambda p: p["rss_mb"], reverse=True)

        # Populate tree with sorted data
        new_selection_id = None
        for proc_data in processes_data:
            pid = proc_data["pid"]
            name = proc_data["name"]
            rss_mb = proc_data["rss_mb"]
            tag = "essential" if proc_data["is_essential"] else "nonessential"

            item_id = self.tree.insert(
                "",
                "end",
                values=(pid, name, f"{rss_mb:.1f}"),
                tags=(tag,),
            )
            if pid == selected_pid:
                new_selection_id = item_id # Store the new item ID

        # Re-select the previously selected item if it still exists
        if new_selection_id:
            self.tree.selection_set(new_selection_id)
            self.tree.see(new_selection_id) # Ensure it's visible

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
