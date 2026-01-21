#!/usr/bin/env python3
"""
SRT Grammar & Spelling Checker - Portable Edition
==================================================

This is a SINGLE-FILE portable version that:
1. Automatically installs required packages on first run
2. Includes all functionality in one file
3. Can be run by double-clicking (on Windows) or via terminal

Requirements:
- Python 3.10 or higher
- Internet connection (for first-time package installation)

Usage:
  python srt_checker_portable.py
  
Or on Windows, just double-click the file!
"""

import subprocess
import sys
import os

# ============================================================================
# DEPENDENCY INSTALLER
# ============================================================================

def check_and_install_packages():
    """Check for required packages and install if missing."""
    packages_to_check = [
        ('google.genai', 'google-genai'),
        ('google.generativeai', 'google-generativeai'),
        ('openai', 'openai')
    ]
    
    installed = []
    for import_name, pip_name in packages_to_check:
        try:
            __import__(import_name)
            installed.append(import_name)
        except ImportError:
            pass
    
    # Check if we have at least one LLM package
    has_gemini = 'google.genai' in installed or 'google.generativeai' in installed
    has_openai = 'openai' in installed
    
    if has_gemini or has_openai:
        return True
    
    # Need to install packages
    print("=" * 60)
    print("SRT Grammar Checker - First Time Setup")
    print("=" * 60)
    print("\nInstalling required packages...")
    print("This only happens once.\n")
    
    # Try to install both packages
    for pip_name in ['google-genai', 'openai']:
        print(f"Installing {pip_name}...")
        try:
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install', pip_name, '--quiet'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"  ✓ {pip_name} installed successfully")
        except subprocess.CalledProcessError:
            print(f"  ✗ Failed to install {pip_name}")
    
    print("\nSetup complete! Starting application...\n")
    return True


# Run dependency check before importing anything else
if __name__ == '__main__':
    check_and_install_packages()

# ============================================================================
# Now import the rest of the modules
# ============================================================================

import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

# Package availability checks
NEW_GENAI_AVAILABLE = False
LEGACY_GENAI_AVAILABLE = False
OPENAI_AVAILABLE = False

try:
    from google import genai
    NEW_GENAI_AVAILABLE = True
except ImportError:
    pass

if not NEW_GENAI_AVAILABLE:
    try:
        import google.generativeai as genai_legacy
        LEGACY_GENAI_AVAILABLE = True
    except ImportError:
        pass

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    pass


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class SubtitleEntry:
    index: int
    timestamp: str
    text: str

@dataclass
class Sentence:
    text: str
    start_index: int
    source_file: str

@dataclass
class TextError:
    source_file: str
    subtitle_index: int
    original_text: str
    error_type: str
    error_description: str
    suggested_correction: str


# ============================================================================
# SRT PARSER
# ============================================================================

class SRTParser:
    TIMESTAMP_PATTERN = re.compile(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})')
    
    def parse_file(self, filepath: str) -> list[SubtitleEntry]:
        entries = []
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        content = None
        
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            raise ValueError(f"Could not decode file {filepath}")
        
        blocks = re.split(r'\n\s*\n', content.strip())
        for block in blocks:
            entry = self._parse_block(block)
            if entry:
                entries.append(entry)
        return entries
    
    def _parse_block(self, block: str) -> SubtitleEntry | None:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            return None
        try:
            index = int(lines[0].strip())
        except ValueError:
            return None
        
        if not self.TIMESTAMP_PATTERN.match(lines[1].strip()):
            return None
        
        timestamp = lines[1].strip()
        text = ' '.join(line.strip() for line in lines[2:] if line.strip())
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\{[^}]+\}', '', text)
        text = ' '.join(text.split())
        
        return SubtitleEntry(index=index, timestamp=timestamp, text=text)


# ============================================================================
# SENTENCE EXTRACTOR
# ============================================================================

class SentenceExtractor:
    SENTENCE_ENDINGS = re.compile(r'[.!?](?:\s|$|"|\')')
    
    # =========================================================================
    # EDIT: Added list of common abbreviations that should NOT end sentences
    # =========================================================================
    ABBREVIATIONS = {
        # Titles
        'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr', 'rev', 'fr', 'st',
        # Military/Government
        'gen', 'col', 'lt', 'sgt', 'capt', 'cmdr', 'adm', 'gov', 'sen', 'rep',
        # Academic
        'ph', 'phd', 'ma', 'ba', 'bs', 'md', 'dds', 'esq',
        # Common abbreviations
        'vs', 'etc', 'inc', 'ltd', 'corp', 'co', 'dept', 'div', 'est', 'vol',
        'no', 'nos', 'fig', 'figs', 'approx', 'appt', 'apt', 'ave', 'blvd',
        'rd', 'st', 'ct', 'ln', 'dr', 'mt', 'ft',
        # Months
        'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec',
        # Time
        'a.m', 'p.m', 'am', 'pm',
        # Other common
        'i.e', 'e.g', 'cf', 'al', 'op', 'cit', 'ibid', 'misc', 'def', 'ref',
    }
    # =========================================================================
    
    def _is_abbreviation(self, text: str, period_pos: int) -> bool:
        """
        EDIT: New method to check if a period is part of an abbreviation.
        """
        if period_pos <= 0:
            return False
        
        # Extract the word before the period
        word_start = period_pos - 1
        while word_start > 0 and text[word_start - 1].isalpha():
            word_start -= 1
        
        word = text[word_start:period_pos].lower()
        
        # Check if it's a known abbreviation
        if word in self.ABBREVIATIONS:
            return True
        
        # Check for single letter abbreviations (like middle initials)
        if len(word) == 1 and word.isalpha():
            return True
        
        # Check for patterns like "U.S." or "U.S.A."
        if period_pos >= 2:
            before = text[max(0, word_start-2):word_start]
            if re.match(r'[A-Za-z]\.', before):
                return True
        
        return False
    # =========================================================================
    
    def extract_sentences(self, entries: list[SubtitleEntry], source_file: str) -> list[Sentence]:
        sentences = []
        current_parts = []
        current_start = None
        
        for entry in entries:
            text = entry.text.strip()
            if not text:
                continue
            
            if current_start is None:
                current_start = entry.index
            
            remaining = text
            while remaining:
                match = self.SENTENCE_ENDINGS.search(remaining)
                if match:
                    end_pos = match.end()
                    period_pos = match.start()
                    
                    # ==========================================================
                    # EDIT: Check if this is an abbreviation before splitting
                    # ==========================================================
                    if remaining[period_pos] == '.' and self._is_abbreviation(remaining, period_pos):
                        # It's an abbreviation - don't split here
                        current_parts.append(remaining[:end_pos].strip())
                        remaining = remaining[end_pos:].strip()
                        continue
                    # ==========================================================
                    
                    current_parts.append(remaining[:end_pos].strip())
                    full = ' '.join(current_parts)
                    full = re.sub(r'\s+([.,!?;:])', r'\1', full)
                    if full:
                        sentences.append(Sentence(text=full, start_index=current_start, source_file=source_file))
                    current_parts = []
                    remaining = remaining[end_pos:].strip()
                    current_start = entry.index if remaining else None
                else:
                    current_parts.append(remaining)
                    break
        
        if current_parts:
            full = ' '.join(current_parts)
            if full:
                sentences.append(Sentence(text=full, start_index=current_start, source_file=source_file))
        
        return sentences


# ============================================================================
# BASE CHECKER
# ============================================================================

class BaseChecker:
    def __init__(self):
        self.check_type = "both"
    
    def set_check_type(self, check_type: str):
        self.check_type = check_type.lower()
    
    def create_prompt(self, sentences: list[Sentence]) -> str:
        sentences_text = "\n".join(f"[{i+1}] (Index {s.start_index}): \"{s.text}\"" for i, s in enumerate(sentences))
        
        if self.check_type == "grammar":
            check_for = "GRAMMAR ONLY: Subject-verb agreement, tense issues, punctuation, word choice, missing words, incorrect plurals, article usage. Do NOT check spelling."
        elif self.check_type == "spelling":
            check_for = "SPELLING ONLY: Misspelled words, typos, incorrect word forms. Do NOT check grammar."
        else:
            check_for = "BOTH grammar AND spelling errors."
        
        return f"""Analyze each sentence for {check_for}

{sentences_text}

For each sentence, respond:
[number]
STATUS: NO_ERRORS or HAS_ERRORS
TYPE: GRAMMAR, SPELLING, or BOTH
ERROR: [description if HAS_ERRORS]
CORRECTION: [corrected sentence if HAS_ERRORS]

Be concise. Don't flag style preferences."""
    
    def parse_response(self, response_text: str, sentences: list[Sentence]) -> list[TextError]:
        errors = []
        blocks = re.split(r'\[(\d+)\]', response_text)
        i = 1
        while i < len(blocks):
            try:
                num = int(blocks[i])
                if i + 1 < len(blocks) and num <= len(sentences):
                    content = blocks[i + 1]
                    if "HAS_ERRORS" in content.upper():
                        sentence = sentences[num - 1]
                        type_match = re.search(r'TYPE:\s*(GRAMMAR|SPELLING|BOTH)', content, re.IGNORECASE)
                        error_match = re.search(r'ERROR:\s*(.+?)(?=CORRECTION:|$)', content, re.IGNORECASE | re.DOTALL)
                        corr_match = re.search(r'CORRECTION:\s*(.+?)(?=\[|$)', content, re.IGNORECASE | re.DOTALL)
                        if error_match:
                            errors.append(TextError(
                                source_file=sentence.source_file,
                                subtitle_index=sentence.start_index,
                                original_text=sentence.text,
                                error_type=type_match.group(1).lower() if type_match else "grammar",
                                error_description=error_match.group(1).strip(),
                                suggested_correction=corr_match.group(1).strip() if corr_match else ""
                            ))
            except (ValueError, IndexError):
                pass
            i += 2
        return errors
    
    def check_sentences_batch(self, sentences: list[Sentence], batch_size: int = 5, progress_callback=None) -> list[TextError]:
        all_errors = []
        for i in range(0, len(sentences), batch_size):
            batch = sentences[i:i + batch_size]
            all_errors.extend(self._check_batch(batch))
            if progress_callback:
                progress_callback(min(i + batch_size, len(sentences)), len(sentences))
        return all_errors
    
    def _check_batch(self, sentences):
        raise NotImplementedError


# ============================================================================
# GEMINI CHECKER
# ============================================================================

class GeminiChecker(BaseChecker):
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        super().__init__()
        self.use_legacy = not NEW_GENAI_AVAILABLE
        if self.use_legacy:
            genai_legacy.configure(api_key=api_key)
            self.model = genai_legacy.GenerativeModel(model_name if model_name != "gemini-2.0-flash" else "gemini-1.5-flash")
        else:
            self.client = genai.Client(api_key=api_key)
            self.model_name = model_name
    
    def _check_batch(self, sentences):
        if not sentences:
            return []
        prompt = self.create_prompt(sentences)
        try:
            if self.use_legacy:
                response = self.model.generate_content(prompt)
                text = response.text
            else:
                response = self.client.models.generate_content(model=self.model_name, contents=prompt)
                text = response.text
            return self.parse_response(text, sentences)
        except Exception as e:
            print(f"Gemini API error: {e}")
            return []


# ============================================================================
# OPENAI CHECKER
# ============================================================================

class OpenAIChecker(BaseChecker):
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        super().__init__()
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name
    
    def _check_batch(self, sentences):
        if not sentences:
            return []
        prompt = self.create_prompt(sentences)
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "system", "content": "You are a grammar/spelling checker. Be concise."},
                          {"role": "user", "content": prompt}],
                temperature=0.1
            )
            return self.parse_response(response.choices[0].message.content, sentences)
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return []


# ============================================================================
# REPORT GENERATOR
# ============================================================================

class ReportGenerator:
    def generate_report(self, errors, output_path, files_processed, total_sentences, llm_provider="", model_name="", check_type=""):
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\nSRT GRAMMAR & SPELLING CHECK ERROR REPORT\n" + "=" * 80 + "\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"LLM Provider: {llm_provider}\nModel: {model_name}\nCheck Type: {check_type}\n")
            f.write(f"Files: {len(files_processed)} | Sentences: {total_sentences} | Errors: {len(errors)}\n\n")
            
            if not errors:
                f.write("No errors found!\n")
            else:
                by_file = {}
                for e in errors:
                    by_file.setdefault(e.source_file, []).append(e)
                for filepath, file_errors in by_file.items():
                    f.write("-" * 80 + f"\nFILE: {os.path.basename(filepath)}\n" + "-" * 80 + "\n")
                    for i, e in enumerate(sorted(file_errors, key=lambda x: x.subtitle_index), 1):
                        f.write(f"\nError #{i}\n  Index: {e.subtitle_index}\n  Type: {e.error_type.upper()}\n")
                        f.write(f"  Original: \"{e.original_text}\"\n  Error: {e.error_description}\n")
                        f.write(f"  Correction: {e.suggested_correction}\n")
            f.write("\n" + "=" * 80 + "\nEND OF REPORT\n" + "=" * 80 + "\n")


# ============================================================================
# GUI APPLICATION
# ============================================================================

class SRTCheckerGUI:
    GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    OPENAI_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SRT Grammar & Spelling Checker")
        self.root.geometry("850x780")
        
        self.folder_path = tk.StringVar()
        self.llm_provider = tk.StringVar(value="Google Gemini")
        self.api_key = tk.StringVar()
        self.selected_model = tk.StringVar(value=self.GEMINI_MODELS[0])
        self.check_type = tk.StringVar(value="Both (Grammar & Spelling)")
        self.files_per_batch = tk.IntVar(value=5)
        self.sentences_per_api = tk.IntVar(value=5)
        self.is_processing = False
        self.last_report = None
        
        self.gemini_key = os.environ.get('GEMINI_API_KEY', '')
        self.openai_key = os.environ.get('OPENAI_API_KEY', '')
        self.api_key.set(self.gemini_key)
        
        self._create_widgets()
        self._on_provider_change()
    
    def _create_widgets(self):
        main = ttk.Frame(self.root, padding="10")
        main.pack(fill=tk.BOTH, expand=True)
        
        # Provider
        pf = ttk.LabelFrame(main, text="LLM Provider", padding="10")
        pf.pack(fill=tk.X, pady=(0, 10))
        pi = ttk.Frame(pf)
        pi.pack(fill=tk.X)
        ttk.Label(pi, text="Provider:").pack(side=tk.LEFT)
        gemini_avail = NEW_GENAI_AVAILABLE or LEGACY_GENAI_AVAILABLE
        self.gemini_radio = ttk.Radiobutton(pi, text="Google Gemini", variable=self.llm_provider, value="Google Gemini", command=self._on_provider_change)
        self.gemini_radio.pack(side=tk.LEFT, padx=(15, 0))
        ttk.Label(pi, text="✓" if gemini_avail else "✗", foreground="green" if gemini_avail else "red").pack(side=tk.LEFT, padx=(2, 15))
        self.openai_radio = ttk.Radiobutton(pi, text="OpenAI", variable=self.llm_provider, value="OpenAI", command=self._on_provider_change)
        self.openai_radio.pack(side=tk.LEFT)
        ttk.Label(pi, text="✓" if OPENAI_AVAILABLE else "✗", foreground="green" if OPENAI_AVAILABLE else "red").pack(side=tk.LEFT, padx=(2, 0))
        mf = ttk.Frame(pf)
        mf.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(mf, text="Model:").pack(side=tk.LEFT)
        self.model_combo = ttk.Combobox(mf, textvariable=self.selected_model, state="readonly", width=25)
        self.model_combo.pack(side=tk.LEFT, padx=(10, 0))
        self.install_hint = ttk.Label(pf, text="", foreground="gray")
        self.install_hint.pack(anchor=tk.W, pady=(5, 0))
        
        # Check type
        cf = ttk.LabelFrame(main, text="Check Type", padding="10")
        cf.pack(fill=tk.X, pady=(0, 10))
        ci = ttk.Frame(cf)
        ci.pack(fill=tk.X)
        ttk.Label(ci, text="What to check:").pack(side=tk.LEFT)
        self.chk_both = ttk.Radiobutton(ci, text="Both", variable=self.check_type, value="Both (Grammar & Spelling)")
        self.chk_both.pack(side=tk.LEFT, padx=(15, 10))
        self.chk_grammar = ttk.Radiobutton(ci, text="Grammar Only", variable=self.check_type, value="Grammar Only")
        self.chk_grammar.pack(side=tk.LEFT, padx=(0, 10))
        self.chk_spelling = ttk.Radiobutton(ci, text="Spelling Only", variable=self.check_type, value="Spelling Only")
        self.chk_spelling.pack(side=tk.LEFT)
        
        # API Key
        af = ttk.LabelFrame(main, text="API Key", padding="10")
        af.pack(fill=tk.X, pady=(0, 10))
        self.api_label = ttk.Label(af, text="API Key:")
        self.api_label.pack(anchor=tk.W)
        ae = ttk.Frame(af)
        ae.pack(fill=tk.X, pady=(5, 0))
        self.api_entry = ttk.Entry(ae, textvariable=self.api_key, show="*", width=60)
        self.api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.show_key = tk.BooleanVar()
        ttk.Checkbutton(ae, text="Show", variable=self.show_key, command=lambda: self.api_entry.config(show="" if self.show_key.get() else "*")).pack(side=tk.LEFT, padx=(5, 0))
        self.api_link = ttk.Label(af, text="", foreground="blue")
        self.api_link.pack(anchor=tk.W, pady=(5, 0))
        
        # Folder
        ff = ttk.LabelFrame(main, text="SRT Files Location", padding="10")
        ff.pack(fill=tk.X, pady=(0, 10))
        fe = ttk.Frame(ff)
        fe.pack(fill=tk.X)
        self.folder_entry = ttk.Entry(fe, textvariable=self.folder_path, width=60)
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.browse_btn = ttk.Button(fe, text="Browse...", command=self._browse)
        self.browse_btn.pack(side=tk.LEFT, padx=(5, 0))
        self.file_count = ttk.Label(ff, text="No folder selected")
        self.file_count.pack(anchor=tk.W, pady=(5, 0))
        
        # Settings
        sf = ttk.LabelFrame(main, text="Settings", padding="10")
        sf.pack(fill=tk.X, pady=(0, 10))
        sg = ttk.Frame(sf)
        sg.pack(fill=tk.X)
        ttk.Label(sg, text="Files per batch:").grid(row=0, column=0)
        ttk.Spinbox(sg, from_=1, to=20, width=8, textvariable=self.files_per_batch).grid(row=0, column=1, padx=(5, 20))
        ttk.Label(sg, text="Sentences per API call:").grid(row=0, column=2)
        ttk.Spinbox(sg, from_=1, to=10, width=8, textvariable=self.sentences_per_api).grid(row=0, column=3, padx=(5, 0))
        
        # Actions
        actf = ttk.LabelFrame(main, text="Actions", padding="15")
        actf.pack(fill=tk.X, pady=(0, 10))
        bc = ttk.Frame(actf)
        bc.pack(fill=tk.X)
        self.start_btn = tk.Button(bc, text="▶ START", command=self._start, font=('Helvetica', 12, 'bold'), bg='#4CAF50', fg='white', padx=20, pady=10)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 15))
        self.stop_btn = tk.Button(bc, text="⏹ STOP", command=self._stop, font=('Helvetica', 10, 'bold'), bg='#f44336', fg='white', padx=15, pady=8, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)
        self.report_btn = tk.Button(bc, text="📄 Open Report", command=self._open_report, font=('Helvetica', 10), bg='#2196F3', fg='white', padx=15, pady=8, state=tk.DISABLED)
        self.report_btn.pack(side=tk.RIGHT)
        
        # Progress
        prf = ttk.LabelFrame(main, text="Progress", padding="10")
        prf.pack(fill=tk.X, pady=(0, 10))
        self.progress_lbl = ttk.Label(prf, text="Ready")
        self.progress_lbl.pack(anchor=tk.W)
        self.progress_bar = ttk.Progressbar(prf, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        self.batch_lbl = ttk.Label(prf, text="")
        self.batch_lbl.pack(anchor=tk.W, pady=(5, 0))
        
        # Log
        lf = ttk.LabelFrame(main, text="Log", padding="10")
        lf.pack(fill=tk.BOTH, expand=True)
        self.log = scrolledtext.ScrolledText(lf, height=8, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)
    
    def _on_provider_change(self):
        p = self.llm_provider.get()
        if p == "Google Gemini":
            self.model_combo['values'] = self.GEMINI_MODELS
            self.selected_model.set(self.GEMINI_MODELS[0])
            self.api_key.set(self.gemini_key)
            self.api_label.config(text="Google Gemini API Key:")
            self.api_link.config(text="Get key: https://aistudio.google.com/app/apikey")
            avail = NEW_GENAI_AVAILABLE or LEGACY_GENAI_AVAILABLE
            self.install_hint.config(text="✓ Ready" if avail else "⚠ Run: pip install google-genai")
        else:
            self.model_combo['values'] = self.OPENAI_MODELS
            self.selected_model.set(self.OPENAI_MODELS[0])
            self.api_key.set(self.openai_key)
            self.api_label.config(text="OpenAI API Key:")
            self.api_link.config(text="Get key: https://platform.openai.com/api-keys")
            self.install_hint.config(text="✓ Ready" if OPENAI_AVAILABLE else "⚠ Run: pip install openai")
    
    def _browse(self):
        folder = filedialog.askdirectory(title="Select SRT Folder")
        if folder:
            self.folder_path.set(folder)
            count = len(list(Path(folder).glob('**/*.srt')))
            self.file_count.config(text=f"Found {count} SRT file(s)" if count else "No SRT files found")
    
    def _log(self, msg):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)
    
    def _start(self):
        p = self.llm_provider.get()
        if p == "Google Gemini" and not (NEW_GENAI_AVAILABLE or LEGACY_GENAI_AVAILABLE):
            messagebox.showerror("Error", "Install: pip install google-genai")
            return
        if p == "OpenAI" and not OPENAI_AVAILABLE:
            messagebox.showerror("Error", "Install: pip install openai")
            return
        if not self.api_key.get().strip():
            messagebox.showerror("Error", "Enter API key")
            return
        if not self.folder_path.get():
            messagebox.showerror("Error", "Select folder")
            return
        
        srt_files = list(Path(self.folder_path.get()).glob('**/*.srt'))
        if not srt_files:
            messagebox.showerror("Error", "No SRT files found")
            return
        
        if p == "Google Gemini":
            self.gemini_key = self.api_key.get().strip()
        else:
            self.openai_key = self.api_key.get().strip()
        
        self.is_processing = True
        for w in [self.start_btn, self.browse_btn, self.gemini_radio, self.openai_radio, self.chk_both, self.chk_grammar, self.chk_spelling]:
            w.config(state=tk.DISABLED)
        self.model_combo.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log.config(state=tk.NORMAL)
        self.log.delete(1.0, tk.END)
        self.log.config(state=tk.DISABLED)
        
        threading.Thread(target=self._process, args=(srt_files,), daemon=True).start()
    
    def _stop(self):
        self.is_processing = False
        self._log("Stopping...")
    
    def _process(self, srt_files):
        provider = self.llm_provider.get()
        model = self.selected_model.get()
        check_type_display = self.check_type.get()
        check_type_internal = "grammar" if "Grammar" in check_type_display else "spelling" if "Spelling" in check_type_display else "both"
        
        try:
            parser = SRTParser()
            extractor = SentenceExtractor()
            reporter = ReportGenerator()
            
            self._log(f"Using {provider} ({model})")
            self._log(f"Check type: {check_type_display}")
            
            if provider == "Google Gemini":
                checker = GeminiChecker(self.api_key.get().strip(), model)
            else:
                checker = OpenAIChecker(self.api_key.get().strip(), model)
            checker.set_check_type(check_type_internal)
            
            all_errors, all_sentences, processed = [], [], []
            fpb = self.files_per_batch.get()
            spa = self.sentences_per_api.get()
            total = len(srt_files)
            batches = (total + fpb - 1) // fpb
            
            for bn in range(batches):
                if not self.is_processing:
                    break
                batch = srt_files[bn*fpb:(bn+1)*fpb]
                self.root.after(0, lambda b=bn+1, t=batches: self.batch_lbl.config(text=f"Batch {b}/{t}"))
                
                for fp in batch:
                    if not self.is_processing:
                        break
                    self._log(f"Processing: {fp.name}")
                    try:
                        entries = parser.parse_file(str(fp))
                        sentences = extractor.extract_sentences(entries, str(fp))
                        all_sentences.extend(sentences)
                        if sentences:
                            errors = checker.check_sentences_batch(sentences, spa, lambda c, t: self.root.after(0, lambda: self.progress_bar.config(value=c/t*100)))
                            all_errors.extend(errors)
                            self._log(f"  Found {len(errors)} error(s)")
                        processed.append(str(fp))
                    except Exception as e:
                        self._log(f"  Error: {e}")
                
                self.root.after(0, lambda p=(bn+1)/batches*100: self.progress_bar.config(value=p))
            
            if processed:
                report_path = os.path.join(self.folder_path.get(), f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                reporter.generate_report(all_errors, report_path, processed, len(all_sentences), provider, model, check_type_display)
                self.last_report = report_path
                self.root.after(0, lambda: self.report_btn.config(state=tk.NORMAL))
                self._log(f"\nDone! Errors: {len(all_errors)}, Report: {os.path.basename(report_path)}")
                self.root.after(0, lambda: messagebox.showinfo("Complete", f"Found {len(all_errors)} errors\nReport: {report_path}"))
        except Exception as e:
            self._log(f"Error: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.is_processing = False
            self.root.after(0, self._reset_ui)
    
    def _reset_ui(self):
        for w in [self.start_btn, self.browse_btn, self.gemini_radio, self.openai_radio, self.chk_both, self.chk_grammar, self.chk_spelling]:
            w.config(state=tk.NORMAL)
        self.model_combo.config(state="readonly")
        self.stop_btn.config(state=tk.DISABLED)
        self.progress_lbl.config(text="Ready")
        self.batch_lbl.config(text="")
    
    def _open_report(self):
        if self.last_report and os.path.exists(self.last_report):
            if sys.platform == 'win32':
                os.startfile(self.last_report)
            elif sys.platform == 'darwin':
                os.system(f'open "{self.last_report}"')
            else:
                os.system(f'xdg-open "{self.last_report}"')
    
    def run(self):
        self.root.mainloop()


def main():
    app = SRTCheckerGUI()
    app.run()


if __name__ == '__main__':
    main()
