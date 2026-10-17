import os
import logging
import customtkinter as ctk

from ui import customTheme
from modules import configuration

logger = logging.getLogger(__name__)


def _parse_filetypes(filetypes):
    if not filetypes:
        return ('.mid', '.midi')
    extensions = []
    for item in filetypes:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            pattern = item[1]
            for pat in pattern.replace(";", " ").split():
                pat = pat.strip()
                if pat.startswith("*."):
                    extensions.append(pat[1:].lower())
                elif pat.startswith("."):
                    extensions.append(pat.lower())
                elif pat and pat != "*":
                    extensions.append("." + pat.lower())
        elif isinstance(item, str):
            item = item.strip().lower()
            if item.startswith("*."):
                extensions.append(item[1:])
            elif item.startswith("."):
                extensions.append(item)
    return tuple(extensions) if extensions else ('.mid', '.midi')


def _resolve_initial_dir(initialdir):
    if initialdir and os.path.isdir(initialdir):
        return os.path.abspath(initialdir)

    try:
        cfg_dir = configuration.configData.get('last_midi_dir')
        if cfg_dir and os.path.isdir(cfg_dir):
            return os.path.abspath(cfg_dir)
    except Exception:
        pass

    try:
        current_midi = configuration.configData.get('midiPlayer', {}).get('currentFile')
        if current_midi and os.path.isfile(current_midi):
            dir_path = os.path.dirname(current_midi)
            if os.path.isdir(dir_path):
                return os.path.abspath(dir_path)
    except Exception:
        pass

    try:
        midis_dir = os.path.join(configuration.baseDirectory, "Midis")
        if os.path.isdir(midis_dir):
            return os.path.abspath(midis_dir)
    except Exception:
        pass

    cwd = os.getcwd()
    if os.path.isdir(cwd):
        return os.path.abspath(cwd)

    return os.path.abspath(os.path.expanduser("~"))


def _calculate_highlight_color(bg_hex):
    try:
        if isinstance(bg_hex, str) and bg_hex.startswith("#"):
            hex_str = bg_hex.lstrip("#")
            if len(hex_str) == 6:
                r = int(hex_str[0:2], 16)
                g = int(hex_str[2:4], 16)
                b = int(hex_str[4:6], 16)
                luminance = 0.299 * r + 0.587 * g + 0.114 * b
                if luminance < 128:
                    return f"#{min(255, r + 45):02x}{min(255, g + 48):02x}{min(255, b + 55):02x}"
                else:
                    return f"#{max(0, r - 35):02x}{max(0, g - 30):02x}{max(0, b - 20):02x}"
    except Exception:
        pass
    return "#2a374a"


class CustomFileDialog(ctk.CTkToplevel):
    def __init__(self, master=None, title="Select MIDI File", initialdir=None, filetypes=None):
        super().__init__(master)
        logger.info("CustomFileDialog initialized")

        self.result = ""
        self.selected_file = None
        self.selected_folder = None
        self.selected_btn = None
        self.allowed_extensions = _parse_filetypes(filetypes)
        self.current_dir = _resolve_initial_dir(initialdir)

        # Theme & Fonts
        try:
            customTheme.initializeFonts()
            self.font12 = customTheme.globalFont12
            self.font14 = customTheme.globalFont14
        except Exception:
            self.font12 = ctk.CTkFont(size=12, weight="bold")
            self.font14 = ctk.CTkFont(size=14, weight="bold")

        theme_midi = customTheme.activeThemeData.get("Theme", {}).get("MidiPlayer", {})
        self.bg_color = theme_midi.get("BackgroundColor", "#0a0a0a")
        self.text_color = theme_midi.get("TextColor", "#ffffff")
        self.text_color_disabled = theme_midi.get("TextColorDisabled", "#737373")
        self.btn_color = theme_midi.get("ButtonColor", "#1a1a1a")
        self.btn_hover_color = theme_midi.get("ButtonHoverColor", "#333333")
        self.highlight_color = _calculate_highlight_color(self.bg_color)

        # Window Configuration
        self.title(title)
        self.configure(fg_color=self.bg_color)
        self.minsize(480, 380)

        width = 580
        height = 480
        self._center_window(master, width, height)

        self.all_folders = []
        self.all_files = []
        self.current_filtered_folders = []
        self.current_filtered_files = []
        self.scan_error = None
        self._filter_after_id = None
        self._is_updating_path = False

        # Layout Setup
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_top_bar()
        self._build_center_list()
        self._build_bottom_bar()

        # Keyboard shortcuts
        self.bind("<Escape>", lambda e: self.on_cancel())

        # Load initial directory contents
        self.navigate_to(self.current_dir)

        # Modal Behavior
        if master:
            self.transient(master)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.wait_window()

    def _center_window(self, master, width, height):
        try:
            if master and master.winfo_exists():
                master_x = master.winfo_rootx()
                master_y = master.winfo_rooty()
                master_w = master.winfo_width()
                master_h = master.winfo_height()
                x = master_x + (master_w - width) // 2
                y = master_y + (master_h - height) // 2
            else:
                screen_w = self.winfo_screenwidth()
                screen_h = self.winfo_screenheight()
                x = (screen_w - width) // 2
                y = (screen_h - height) // 2
            self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        except Exception:
            self.geometry(f"{width}x{height}")

    def _build_top_bar(self):
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 8))
        top_frame.grid_columnconfigure(1, weight=1)

        self.up_btn = ctk.CTkButton(
            top_frame,
            text="⤴",
            width=36,
            height=32,
            font=self.font14,
            fg_color=self.btn_color,
            hover_color=self.btn_hover_color,
            text_color=self.text_color,
            text_color_disabled=self.text_color_disabled,
            command=self.go_up
        )
        self.up_btn.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.path_entry = ctk.CTkEntry(
            top_frame,
            height=32,
            font=self.font12,
            text_color=self.text_color,
            fg_color=self.btn_color,
            border_width=1,
            border_color=self.btn_hover_color
        )
        self.path_entry.grid(row=0, column=1, sticky="ew")
        self.path_entry.bind("<KeyRelease>", self._on_path_key_release)
        self.path_entry.bind("<Return>", self._on_path_entry_return)

    def _on_path_key_release(self, event=None):
        if self._is_updating_path:
            return

        if event and event.keysym in ("Return", "Escape", "Tab", "Up", "Down", "Left", "Right"):
            return

        if self._filter_after_id is not None:
            try:
                self.after_cancel(self._filter_after_id)
            except Exception:
                pass
            self._filter_after_id = None

        self._filter_after_id = self.after(250, self._apply_path_filter)

    def _apply_path_filter(self):
        self._filter_after_id = None
        if not hasattr(self, "path_entry") or not self.path_entry.winfo_exists():
            return

        raw_text = self.path_entry.get().strip()

        if not raw_text or raw_text == self.current_dir:
            self.filter_list("")
            return

        if raw_text.startswith(self.current_dir + os.sep) or raw_text.startswith(self.current_dir + "/"):
            sub = raw_text[len(self.current_dir):].lstrip("/\\")
            self.filter_list(sub)
            return

        if "/" in raw_text or "\\" in raw_text or raw_text.startswith("~"):
            expanded = os.path.expanduser(raw_text)
            basename = os.path.basename(expanded)
            self.filter_list(basename)
            return

        self.filter_list(raw_text)

    def _on_path_entry_return(self, event=None):
        if self._filter_after_id is not None:
            try:
                self.after_cancel(self._filter_after_id)
            except Exception:
                pass
            self._filter_after_id = None
            self._apply_path_filter()

        raw_text = self.path_entry.get().strip()
        if not raw_text:
            self._update_path_display()
            self.filter_list("")
            return

        expanded = os.path.abspath(os.path.expanduser(raw_text))

        # 1. Valid directory: navigate to it
        if os.path.isdir(expanded):
            self.navigate_to(expanded)
            return

        # 2. Valid file: select and confirm it
        if os.path.isfile(expanded):
            self.selected_file = expanded
            self.on_select()
            return

        # 3. Check directly in current directory
        in_current = os.path.join(self.current_dir, raw_text)
        if os.path.isdir(in_current):
            self.navigate_to(in_current)
            return
        if os.path.isfile(in_current):
            self.selected_file = in_current
            self.on_select()
            return

        # 4. Check filtered list: if exactly one match, navigate or select it
        filtered_folders = getattr(self, "current_filtered_folders", [])
        filtered_files = getattr(self, "current_filtered_files", [])

        if len(filtered_folders) == 1 and len(filtered_files) == 0:
            self.navigate_to(os.path.join(self.current_dir, filtered_folders[0]))
            return
        elif len(filtered_files) == 1 and len(filtered_folders) == 0:
            self.selected_file = os.path.join(self.current_dir, filtered_files[0])
            self.on_select()
            return
        elif (len(filtered_folders) + len(filtered_files)) == 1:
            if filtered_folders:
                self.navigate_to(os.path.join(self.current_dir, filtered_folders[0]))
            else:
                self.selected_file = os.path.join(self.current_dir, filtered_files[0])
                self.on_select()
            return

        # Revert path entry to current_dir and clear filter
        self._update_path_display()
        self.filter_list("")

    def _update_path_display(self):
        self._is_updating_path = True
        try:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, self.current_dir)
        finally:
            self._is_updating_path = False

    def _build_center_list(self):
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=self.bg_color,
            corner_radius=6,
            border_width=1,
            border_color=self.btn_hover_color
        )
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))

    def _build_bottom_bar(self):
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))
        bottom_frame.grid_columnconfigure(1, weight=1)

        # File name input row
        file_label = ctk.CTkLabel(
            bottom_frame,
            text="File name:",
            font=self.font12,
            text_color=self.text_color
        )
        file_label.grid(row=0, column=0, padx=(0, 8), pady=(0, 10), sticky="w")

        self.filename_entry = ctk.CTkEntry(
            bottom_frame,
            height=32,
            font=self.font12,
            text_color=self.text_color,
            fg_color=self.btn_color,
            border_width=1,
            border_color=self.btn_hover_color
        )
        self.filename_entry.grid(row=0, column=1, columnspan=2, pady=(0, 10), sticky="ew")
        self.filename_entry.bind("<Return>", lambda e: self.on_select())

        # Action buttons row
        btn_box = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        btn_box.grid(row=1, column=0, columnspan=3, sticky="e")

        self.select_btn = ctk.CTkButton(
            btn_box,
            text="Select",
            width=90,
            height=32,
            font=self.font14,
            fg_color=self.btn_color,
            hover_color=self.btn_hover_color,
            text_color=self.text_color,
            text_color_disabled=self.text_color_disabled,
            command=self.on_select,
            state="disabled"
        )
        self.select_btn.pack(side="left", padx=(0, 8))

        self.cancel_btn = ctk.CTkButton(
            btn_box,
            text="Cancel",
            width=90,
            height=32,
            font=self.font14,
            fg_color=self.btn_color,
            hover_color=self.btn_hover_color,
            text_color=self.text_color,
            command=self.on_cancel
        )
        self.cancel_btn.pack(side="left")

    def go_up(self):
        parent = os.path.dirname(self.current_dir)
        if parent and parent != self.current_dir and os.path.isdir(parent):
            self.navigate_to(parent)

    def navigate_to(self, target_dir):
        if not os.path.isdir(target_dir):
            return

        if self._filter_after_id is not None:
            try:
                self.after_cancel(self._filter_after_id)
            except Exception:
                pass
            self._filter_after_id = None

        self._is_updating_path = True
        try:
            self.current_dir = os.path.abspath(target_dir)
            self._update_path_display()
        finally:
            self._is_updating_path = False

        # Check if Up button should be enabled
        parent = os.path.dirname(self.current_dir)
        if parent == self.current_dir:
            self.up_btn.configure(state="disabled")
        else:
            self.up_btn.configure(state="normal")

        # Reset selection state
        self.selected_file = None
        self.selected_folder = None
        self.selected_btn = None
        self.filename_entry.delete(0, "end")
        self.select_btn.configure(state="disabled")

        self.scan_directory()
        self.render_list()

    def scan_directory(self):
        self.all_folders = []
        self.all_files = []
        self.scan_error = None

        try:
            with os.scandir(self.current_dir) as entries:
                for entry in entries:
                    try:
                        name = entry.name
                        if name.startswith('.'):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            self.all_folders.append(name)
                        elif entry.is_file(follow_symlinks=False):
                            lower_name = name.lower()
                            if any(lower_name.endswith(ext) for ext in self.allowed_extensions):
                                self.all_files.append(name)
                    except OSError:
                        continue
        except (PermissionError, OSError) as e:
            logger.warning(f"Error accessing directory '{self.current_dir}': {e}")
            self.scan_error = str(e)
            return

        self.all_folders.sort(key=str.lower)
        self.all_files.sort(key=str.lower)
        self.current_filtered_folders = list(self.all_folders)
        self.current_filtered_files = list(self.all_files)

    def filter_list(self, query):
        if not query or not query.strip():
            self.render_list(self.all_folders, self.all_files)
            return

        q = query.strip().lower()
        filtered_folders = [f for f in self.all_folders if q in f.lower()]
        filtered_files = [f for f in self.all_files if q in f.lower()]
        self.render_list(filtered_folders, filtered_files)

    def render_list(self, folders=None, files=None):
        if folders is None:
            folders = self.all_folders
        if files is None:
            files = self.all_files

        self.current_filtered_folders = list(folders)
        self.current_filtered_files = list(files)

        # Clear existing entries in scroll frame
        for child in self.scroll_frame.winfo_children():
            child.destroy()

        self.selected_btn = None

        if self.scan_error:
            err_lbl = ctk.CTkLabel(
                self.scroll_frame,
                text=f"Cannot access directory: {self.scan_error}",
                font=self.font12,
                text_color=self.text_color_disabled
            )
            err_lbl.pack(pady=20, padx=10)
            self.after(10, lambda: self.scroll_frame._parent_canvas.yview_moveto(0.0))
            return

        current_text = self.path_entry.get().strip() if hasattr(self, "path_entry") else ""
        is_searching = bool(current_text and current_text != self.current_dir)

        if not folders and not files:
            msg = "No matching files or folders found" if is_searching else "Folder is empty or contains no MIDI files"
            empty_lbl = ctk.CTkLabel(
                self.scroll_frame,
                text=msg,
                font=self.font12,
                text_color=self.text_color_disabled
            )
            empty_lbl.pack(pady=30, padx=10)
            if self.selected_file:
                self.select_btn.configure(state="disabled")
            self.after(10, lambda: self.scroll_frame._parent_canvas.yview_moveto(0.0))
            return

        # Cap items to prevent UI freezing if directory is extraordinarily large
        MAX_ITEMS = 1000
        total_count = len(folders) + len(files)
        display_folders = folders[:MAX_ITEMS]
        remaining = max(0, MAX_ITEMS - len(display_folders))
        display_files = files[:remaining]

        selected_file_found = False

        for folder_name in display_folders:
            fpath = os.path.join(self.current_dir, folder_name)
            btn = ctk.CTkButton(
                self.scroll_frame,
                text=f"📁  {folder_name}",
                anchor="w",
                height=28,
                corner_radius=4,
                font=self.font12,
                fg_color="transparent",
                hover_color=self.btn_hover_color,
                text_color=self.text_color,
                border_width=0
            )
            btn.pack(fill="x", pady=1, padx=2)
            btn.bind("<Double-Button-1>", lambda e, p=fpath: self.navigate_to(p))
            btn.configure(command=lambda p=fpath, b=btn: self.on_folder_click(p, b))

        for file_name in display_files:
            fpath = os.path.join(self.current_dir, file_name)
            is_selected = (self.selected_file is not None and os.path.abspath(fpath) == os.path.abspath(self.selected_file))
            btn_fg = self.highlight_color if is_selected else "transparent"

            btn = ctk.CTkButton(
                self.scroll_frame,
                text=f"🎵  {file_name}",
                anchor="w",
                height=28,
                corner_radius=4,
                font=self.font12,
                fg_color=btn_fg,
                hover_color=self.btn_hover_color,
                text_color=self.text_color,
                border_width=0
            )
            btn.pack(fill="x", pady=1, padx=2)
            btn.bind("<Double-Button-1>", lambda e, p=fpath: self.on_file_double_click(p))
            btn.configure(command=lambda p=fpath, b=btn: self.on_file_click(p, b))

            if is_selected:
                self.selected_btn = btn
                selected_file_found = True

        if total_count > MAX_ITEMS:
            more_lbl = ctk.CTkLabel(
                self.scroll_frame,
                text=f"... and {total_count - MAX_ITEMS} more items",
                font=self.font12,
                text_color=self.text_color_disabled
            )
            more_lbl.pack(pady=8)

        # Update Select button state based on whether selected file is visible
        if self.selected_file:
            if selected_file_found:
                self.select_btn.configure(state="normal")
            else:
                self.select_btn.configure(state="disabled")

        # Reset scroll position to top
        self.after(10, lambda: self.scroll_frame._parent_canvas.yview_moveto(0.0))

    def on_folder_click(self, folder_path, btn):
        if self.selected_btn and self.selected_btn.winfo_exists():
            self.selected_btn.configure(fg_color="transparent")
        self.selected_btn = btn
        btn.configure(fg_color=self.highlight_color)
        self.selected_folder = folder_path
        self.selected_file = None
        self.filename_entry.delete(0, "end")
        self.select_btn.configure(state="normal")

    def on_file_click(self, file_path, btn):
        if self.selected_btn and self.selected_btn.winfo_exists():
            self.selected_btn.configure(fg_color="transparent")
        self.selected_btn = btn
        btn.configure(fg_color=self.highlight_color)
        self.selected_file = file_path
        self.selected_folder = None
        self.filename_entry.delete(0, "end")
        self.filename_entry.insert(0, os.path.basename(file_path))
        self.select_btn.configure(state="normal")

    def on_file_double_click(self, file_path):
        self.selected_file = file_path
        self.on_select()

    def on_select(self):
        entered = self.filename_entry.get().strip()
        if entered:
            candidate = os.path.join(self.current_dir, entered)
            if os.path.isfile(candidate):
                self.selected_file = candidate
            elif os.path.isdir(candidate):
                self.navigate_to(candidate)
                return

        if self.selected_file and os.path.isfile(self.selected_file):
            self.result = os.path.abspath(self.selected_file)
            try:
                chosen_dir = os.path.dirname(self.result)
                configuration.configData['last_midi_dir'] = chosen_dir
                configuration.configData.save()
            except Exception as e:
                logger.debug(f"Failed to save last_midi_dir: {e}")
            self._close_dialog()
        elif self.selected_folder and os.path.isdir(self.selected_folder):
            self.navigate_to(self.selected_folder)

    def on_cancel(self):
        self.result = ""
        self._close_dialog()

    def _close_dialog(self):
        if self._filter_after_id is not None:
            try:
                self.after_cancel(self._filter_after_id)
            except Exception:
                pass
            self._filter_after_id = None
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def askopenfilename(title="Select MIDI File", initialdir=None, filetypes=None, master=None) -> str:
    if master is None:
        try:
            from modules.functions import mainFunctions
            master = mainFunctions.getApp()
        except Exception:
            master = None
    dialog = CustomFileDialog(master=master, title=title, initialdir=initialdir, filetypes=filetypes)
    return dialog.result


CustomFileDialog.askopenfilename = staticmethod(askopenfilename)
