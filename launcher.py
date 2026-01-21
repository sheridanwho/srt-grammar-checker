#!/usr/bin/env python3
"""
SRT Grammar Checker Launcher

This launcher script:
1. Checks if required packages are installed
2. Installs missing packages automatically
3. Launches the main application

This is the entry point for the packaged executable.
"""

import subprocess
import sys
import os
import importlib.util
import tkinter as tk
from tkinter import ttk, messagebox
import threading

# Required packages
REQUIRED_PACKAGES = {
    'google-genai': 'google.genai',
    'google-generativeai': 'google.generativeai',  # Fallback
    'openai': 'openai'
}

# Minimum required - at least one LLM package
LLM_PACKAGES = {
    'google-genai': 'google.genai',
    'openai': 'openai'
}


def is_package_installed(import_name):
    """Check if a package is installed by trying to import it."""
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False


def install_package(package_name, progress_callback=None):
    """Install a package using pip."""
    try:
        if progress_callback:
            progress_callback(f"Installing {package_name}...")
        
        # Use subprocess to run pip
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', package_name, '--quiet'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            if progress_callback:
                progress_callback(f"Successfully installed {package_name}")
            return True
        else:
            if progress_callback:
                progress_callback(f"Failed to install {package_name}: {result.stderr}")
            return False
    except Exception as e:
        if progress_callback:
            progress_callback(f"Error installing {package_name}: {str(e)}")
        return False


def check_and_install_dependencies():
    """Check for required packages and install if missing."""
    
    # Check if at least one LLM package is available
    gemini_installed = is_package_installed('google.genai') or is_package_installed('google.generativeai')
    openai_installed = is_package_installed('openai')
    
    if gemini_installed or openai_installed:
        # At least one package is available, we can proceed
        return True, []
    
    # No LLM packages installed, need to install
    missing = []
    if not gemini_installed:
        missing.append('google-genai')
    if not openai_installed:
        missing.append('openai')
    
    return False, missing


class InstallerGUI:
    """GUI for installing dependencies."""
    
    def __init__(self, missing_packages):
        self.missing_packages = missing_packages
        self.root = tk.Tk()
        self.root.title("SRT Grammar Checker - Setup")
        self.root.geometry("500x300")
        self.root.resizable(False, False)
        
        # Center window
        self.root.eval('tk::PlaceWindow . center')
        
        self.install_success = False
        self._create_widgets()
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="SRT Grammar & Spelling Checker",
            font=('Helvetica', 14, 'bold')
        )
        title_label.pack(pady=(0, 10))
        
        # Message
        msg = "The following packages need to be installed:"
        msg_label = ttk.Label(main_frame, text=msg)
        msg_label.pack(pady=(0, 10))
        
        # Package list
        pkg_frame = ttk.Frame(main_frame)
        pkg_frame.pack(pady=(0, 10))
        
        for pkg in self.missing_packages:
            pkg_label = ttk.Label(pkg_frame, text=f"  • {pkg}")
            pkg_label.pack(anchor=tk.W)
        
        # Progress
        self.progress_label = ttk.Label(main_frame, text="Click 'Install' to continue...")
        self.progress_label.pack(pady=(10, 5))
        
        self.progress_bar = ttk.Progressbar(main_frame, mode='indeterminate', length=300)
        self.progress_bar.pack(pady=(0, 10))
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=(10, 0))
        
        self.install_btn = ttk.Button(btn_frame, text="Install", command=self._start_install)
        self.install_btn.pack(side=tk.LEFT, padx=5)
        
        self.skip_btn = ttk.Button(btn_frame, text="Skip (Limited Features)", command=self._skip)
        self.skip_btn.pack(side=tk.LEFT, padx=5)
        
        self.cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self._cancel)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
    
    def _update_progress(self, message):
        self.root.after(0, lambda: self.progress_label.config(text=message))
    
    def _start_install(self):
        self.install_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.progress_bar.start()
        
        thread = threading.Thread(target=self._install_packages)
        thread.daemon = True
        thread.start()
    
    def _install_packages(self):
        success_count = 0
        
        for pkg in self.missing_packages:
            self._update_progress(f"Installing {pkg}...")
            if install_package(pkg, self._update_progress):
                success_count += 1
        
        self.root.after(0, self.progress_bar.stop)
        
        if success_count > 0:
            self._update_progress("Installation complete!")
            self.install_success = True
            self.root.after(1000, self.root.destroy)
        else:
            self._update_progress("Installation failed. Please install manually.")
            self.root.after(0, lambda: self.install_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.skip_btn.config(state=tk.NORMAL))
    
    def _skip(self):
        self.install_success = True  # Allow app to run with limited features
        self.root.destroy()
    
    def _cancel(self):
        self.install_success = False
        self.root.destroy()
    
    def run(self):
        self.root.mainloop()
        return self.install_success


def launch_main_app():
    """Launch the main SRT Grammar Checker application."""
    # Determine the base path (works for both regular Python and PyInstaller)
    if getattr(sys, 'frozen', False):
        # Running as a bundled executable
        base_path = sys._MEIPASS
    else:
        # Running as a regular Python script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    # Path to the main application module
    module_path = os.path.join(base_path, 'srt_grammar_checker_gui.py')
    
    if os.path.exists(module_path):
        # Load the module dynamically
        spec = importlib.util.spec_from_file_location("srt_grammar_checker_gui", module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["srt_grammar_checker_gui"] = module
        spec.loader.exec_module(module)
        module.main()
    else:
        # Try direct import (for development)
        try:
            import srt_grammar_checker_gui
            srt_grammar_checker_gui.main()
        except ImportError:
            messagebox.showerror(
                "Error",
                f"Could not load the main application.\n\n"
                f"Expected location: {module_path}\n\n"
                "Please ensure srt_grammar_checker_gui.py is in the same directory."
            )
            sys.exit(1)


def main():
    """Main entry point."""
    # Check dependencies
    all_installed, missing = check_and_install_dependencies()
    
    if not all_installed and missing:
        # Show installer GUI
        installer = InstallerGUI(missing)
        if not installer.run():
            sys.exit(0)  # User cancelled
    
    # Launch main application
    launch_main_app()


if __name__ == '__main__':
    main()
