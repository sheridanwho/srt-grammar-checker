#!/usr/bin/env python3
"""
SRT Grammar & Spelling Checker GUI

A GUI application that:
1. Allows selecting a folder containing SRT files
2. Supports both Google Gemini and OpenAI APIs
3. Has input fields for API keys
4. Processes SRT files in batches (configurable)
5. Checks for both grammar AND spelling errors
6. Generates detailed error reports

Requirements:
    For Google Gemini:
        pip install google-genai
        Or legacy: pip install google-generativeai
    
    For OpenAI:
        pip install openai
"""

import os
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

# ============================================================================
# Package Availability Checks
# ============================================================================

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
# Data Classes
# ============================================================================

@dataclass
class SubtitleEntry:
    """Represents a single subtitle entry from an SRT file."""
    index: int
    timestamp: str
    text: str


@dataclass
class Sentence:
    """Represents an extracted sentence with its source information."""
    text: str
    start_index: int
    source_file: str


@dataclass
class TextError:
    """Represents a grammar or spelling error found in a sentence."""
    source_file: str
    subtitle_index: int
    original_text: str
    error_type: str  # "grammar" or "spelling" or "both"
    error_description: str
    suggested_correction: str


# ============================================================================
# SRT Parser
# ============================================================================

class SRTParser:
    """Parses SRT files and extracts subtitle entries."""
    
    TIMESTAMP_PATTERN = re.compile(
        r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})'
    )
    
    def parse_file(self, filepath: str) -> list[SubtitleEntry]:
        """Parse an SRT file and return a list of subtitle entries."""
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
        """Parse a single subtitle block."""
        lines = block.strip().split('\n')
        
        if len(lines) < 3:
            return None
        
        try:
            index = int(lines[0].strip())
        except ValueError:
            return None
        
        timestamp_match = self.TIMESTAMP_PATTERN.match(lines[1].strip())
        if not timestamp_match:
            return None
        
        timestamp = lines[1].strip()
        text_lines = lines[2:]
        text = ' '.join(line.strip() for line in text_lines if line.strip())
        text = self._clean_text(text)
        
        return SubtitleEntry(index=index, timestamp=timestamp, text=text)
    
    def _clean_text(self, text: str) -> str:
        """Remove common SRT formatting tags."""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\{[^}]+\}', '', text)
        text = ' '.join(text.split())
        return text.strip()


# ============================================================================
# Sentence Extractor
# ============================================================================

class SentenceExtractor:
    """Extracts complete sentences from subtitle entries."""
    
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
        Returns True if the period at period_pos is likely part of an abbreviation.
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
        
        # Check for single letter abbreviations (like middle initials: "John F. Kennedy")
        if len(word) == 1 and word.isalpha():
            return True
        
        # Check for patterns like "U.S." or "U.S.A." (letters with periods)
        if period_pos >= 2:
            # Look back to see if there's a pattern like "X." before this
            before = text[max(0, word_start-2):word_start]
            if re.match(r'[A-Za-z]\.', before):
                return True
        
        return False
    # =========================================================================
    
    def extract_sentences(self, entries: list[SubtitleEntry], source_file: str) -> list[Sentence]:
        """Extract complete sentences from subtitle entries."""
        sentences = []
        current_sentence_parts = []
        current_start_index = None
        
        for entry in entries:
            text = entry.text.strip()
            if not text:
                continue
            
            if current_start_index is None:
                current_start_index = entry.index
            
            remaining_text = text
            
            while remaining_text:
                match = self.SENTENCE_ENDINGS.search(remaining_text)
                
                if match:
                    end_pos = match.end()
                    period_pos = match.start()
                    
                    # ==========================================================
                    # EDIT: Check if this is an abbreviation before splitting
                    # ==========================================================
                    # Get the full text so far to check for abbreviations
                    full_text_so_far = ' '.join(current_sentence_parts + [remaining_text[:end_pos]])
                    actual_period_pos = len(full_text_so_far) - (end_pos - period_pos)
                    
                    # Check if period is part of an abbreviation
                    if remaining_text[period_pos] == '.' and self._is_abbreviation(remaining_text, period_pos):
                        # It's an abbreviation - don't split here, continue accumulating
                        current_sentence_parts.append(remaining_text[:end_pos].strip())
                        remaining_text = remaining_text[end_pos:].strip()
                        continue
                    # ==========================================================
                    
                    sentence_part = remaining_text[:end_pos].strip()
                    current_sentence_parts.append(sentence_part)
                    
                    full_sentence = ' '.join(current_sentence_parts)
                    full_sentence = self._normalize_sentence(full_sentence)
                    
                    if full_sentence:
                        sentences.append(Sentence(
                            text=full_sentence,
                            start_index=current_start_index,
                            source_file=source_file
                        ))
                    
                    current_sentence_parts = []
                    remaining_text = remaining_text[end_pos:].strip()
                    
                    if remaining_text:
                        current_start_index = entry.index
                    else:
                        current_start_index = None
                else:
                    current_sentence_parts.append(remaining_text)
                    break
        
        if current_sentence_parts:
            full_sentence = ' '.join(current_sentence_parts)
            full_sentence = self._normalize_sentence(full_sentence)
            if full_sentence:
                sentences.append(Sentence(
                    text=full_sentence,
                    start_index=current_start_index,
                    source_file=source_file
                ))
        
        return sentences
    
    def _normalize_sentence(self, text: str) -> str:
        """Normalize whitespace and formatting."""
        text = ' '.join(text.split())
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        return text.strip()


# ============================================================================
# Base Checker Class
# ============================================================================

class BaseChecker:
    """Base class for grammar and spelling checkers."""
    
    def __init__(self):
        self.check_type = "both"  # Default: both grammar and spelling
    
    def set_check_type(self, check_type: str):
        """Set the type of check to perform: 'both', 'grammar', or 'spelling'."""
        self.check_type = check_type.lower()
    
    def create_prompt(self, sentences: list[Sentence]) -> str:
        """Create a prompt based on the check type."""
        sentences_text = "\n".join(
            f"[{i+1}] (Index {s.start_index}): \"{s.text}\""
            for i, s in enumerate(sentences)
        )
        
        if self.check_type == "grammar":
            return self._create_grammar_only_prompt(sentences_text)
        elif self.check_type == "spelling":
            return self._create_spelling_only_prompt(sentences_text)
        else:
            return self._create_both_prompt(sentences_text)
    
    def _create_both_prompt(self, sentences_text: str) -> str:
        """Create a prompt for checking both grammar AND spelling."""
        return f"""You are a grammar and spelling checker. Analyze each of the following sentences for BOTH grammar errors AND spelling errors.

{sentences_text}

For each sentence, respond in this EXACT format:

[sentence_number]
STATUS: NO_ERRORS or HAS_ERRORS
TYPE: [if HAS_ERRORS, specify "GRAMMAR", "SPELLING", or "BOTH"]
ERROR: [if HAS_ERRORS, brief description of the error(s)]
CORRECTION: [if HAS_ERRORS, the fully corrected sentence]

Check for:
- GRAMMAR: Subject-verb agreement, tense issues, punctuation, word choice, missing words, incorrect plurals, article usage
- SPELLING: Misspelled words, typos, incorrect word forms

Do not flag stylistic preferences or regional variations (e.g., British vs American spelling).
Be concise and specific. List all errors found in each sentence."""
    
    def _create_grammar_only_prompt(self, sentences_text: str) -> str:
        """Create a prompt for checking grammar only."""
        return f"""You are a grammar checker. Analyze each of the following sentences for grammar errors ONLY. Do NOT check for spelling errors.

{sentences_text}

For each sentence, respond in this EXACT format:

[sentence_number]
STATUS: NO_ERRORS or HAS_ERRORS
TYPE: GRAMMAR
ERROR: [if HAS_ERRORS, brief description of the grammar error(s)]
CORRECTION: [if HAS_ERRORS, the fully corrected sentence]

Check for grammar issues such as:
- Subject-verb agreement
- Tense issues and inconsistencies
- Punctuation errors
- Word choice errors
- Missing or extra words
- Incorrect plurals
- Article usage (a, an, the)
- Sentence structure problems

Do not flag spelling errors, stylistic preferences, or regional variations.
Be concise and specific."""
    
    def _create_spelling_only_prompt(self, sentences_text: str) -> str:
        """Create a prompt for checking spelling only."""
        return f"""You are a spelling checker. Analyze each of the following sentences for spelling errors ONLY. Do NOT check for grammar errors.

{sentences_text}

For each sentence, respond in this EXACT format:

[sentence_number]
STATUS: NO_ERRORS or HAS_ERRORS
TYPE: SPELLING
ERROR: [if HAS_ERRORS, brief description of the spelling error(s)]
CORRECTION: [if HAS_ERRORS, the fully corrected sentence]

Check for spelling issues such as:
- Misspelled words
- Typos
- Incorrect word forms
- Commonly confused words (e.g., their/there/they're)

Do not flag grammar errors, stylistic preferences, or regional variations (e.g., British vs American spelling).
Be concise and specific."""
    
    def parse_response(self, response_text: str, sentences: list[Sentence]) -> list[TextError]:
        """Parse the API response for grammar and spelling errors."""
        errors = []
        blocks = re.split(r'\[(\d+)\]', response_text)
        
        i = 1
        while i < len(blocks):
            try:
                sentence_num = int(blocks[i])
                if i + 1 < len(blocks):
                    block_content = blocks[i + 1]
                    
                    if sentence_num <= len(sentences) and "HAS_ERRORS" in block_content.upper():
                        sentence = sentences[sentence_num - 1]
                        
                        # Extract error type
                        type_match = re.search(r'TYPE:\s*(GRAMMAR|SPELLING|BOTH)', block_content, re.IGNORECASE)
                        error_type = type_match.group(1).lower() if type_match else "grammar"
                        
                        # Extract error and correction
                        error_match = re.search(r'ERROR:\s*(.+?)(?=CORRECTION:|$)', block_content, re.IGNORECASE | re.DOTALL)
                        correction_match = re.search(r'CORRECTION:\s*(.+?)(?=\[|$)', block_content, re.IGNORECASE | re.DOTALL)
                        
                        if error_match:
                            errors.append(TextError(
                                source_file=sentence.source_file,
                                subtitle_index=sentence.start_index,
                                original_text=sentence.text,
                                error_type=error_type,
                                error_description=error_match.group(1).strip(),
                                suggested_correction=correction_match.group(1).strip() if correction_match else "No correction provided"
                            ))
            except (ValueError, IndexError):
                pass
            i += 2
        
        return errors
    
    def check_sentences_batch(self, sentences: list[Sentence], batch_size: int = 5,
                              progress_callback: Callable[[int, int], None] = None) -> list[TextError]:
        """Check multiple sentences in batches."""
        all_errors = []
        
        for i in range(0, len(sentences), batch_size):
            batch = sentences[i:i + batch_size]
            batch_errors = self._check_batch(batch)
            all_errors.extend(batch_errors)
            
            if progress_callback:
                progress_callback(min(i + batch_size, len(sentences)), len(sentences))
        
        return all_errors
    
    def _check_batch(self, sentences: list[Sentence]) -> list[TextError]:
        """Check a batch of sentences. Override in subclasses."""
        raise NotImplementedError


# ============================================================================
# Google Gemini Checker
# ============================================================================

class GeminiChecker(BaseChecker):
    """Uses Google Gemini API to check grammar and spelling."""
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        """Initialize the checker."""
        super().__init__()
        self.use_legacy = not NEW_GENAI_AVAILABLE
        
        if self.use_legacy:
            if not LEGACY_GENAI_AVAILABLE:
                raise ImportError("No Gemini package available. Install google-genai or google-generativeai")
            genai_legacy.configure(api_key=api_key)
            if model_name == "gemini-2.0-flash":
                model_name = "gemini-1.5-flash"
            self.model = genai_legacy.GenerativeModel(model_name)
        else:
            self.client = genai.Client(api_key=api_key)
            self.model_name = model_name
    
    def _check_batch(self, sentences: list[Sentence]) -> list[TextError]:
        """Check a batch of sentences using Gemini."""
        if not sentences:
            return []
        
        prompt = self.create_prompt(sentences)
        
        try:
            if self.use_legacy:
                response = self.model.generate_content(prompt)
                response_text = response.text
            else:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                response_text = response.text
            
            return self.parse_response(response_text, sentences)
        except Exception as e:
            print(f"Warning: Gemini API error: {e}")
            return []


# ============================================================================
# OpenAI Checker
# ============================================================================

class OpenAIChecker(BaseChecker):
    """Uses OpenAI API to check grammar and spelling."""
    
    # Available models
    MODELS = [
        "gpt-4o",
        "gpt-4o-mini", 
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ]
    
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        """Initialize the checker."""
        super().__init__()
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI package not available. Install with: pip install openai")
        
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name
    
    def _check_batch(self, sentences: list[Sentence]) -> list[TextError]:
        """Check a batch of sentences using OpenAI."""
        if not sentences:
            return []
        
        prompt = self.create_prompt(sentences)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a professional grammar and spelling checker. Be thorough but concise."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1  # Low temperature for consistent results
            )
            
            response_text = response.choices[0].message.content
            return self.parse_response(response_text, sentences)
        except Exception as e:
            print(f"Warning: OpenAI API error: {e}")
            return []


# ============================================================================
# Report Generator
# ============================================================================

class ReportGenerator:
    """Generates error reports in text format."""
    
    def generate_report(self, errors: list[TextError], output_path: str, 
                       files_processed: list[str], total_sentences: int,
                       llm_provider: str = "Unknown", model_name: str = "Unknown",
                       check_type: str = "Both"):
        """Generate a comprehensive error report."""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 80 + "\n")
            f.write("SRT GRAMMAR & SPELLING CHECK ERROR REPORT\n")
            f.write("=" * 80 + "\n\n")
            
            # Summary
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"LLM Provider: {llm_provider}\n")
            f.write(f"Model: {model_name}\n")
            f.write(f"Check Type: {check_type}\n")
            f.write(f"Files processed: {len(files_processed)}\n")
            f.write(f"Total sentences checked: {total_sentences}\n")
            f.write(f"Total errors found: {len(errors)}\n")
            
            # Count by type
            grammar_count = sum(1 for e in errors if e.error_type in ['grammar', 'both'])
            spelling_count = sum(1 for e in errors if e.error_type in ['spelling', 'both'])
            f.write(f"  - Grammar errors: {grammar_count}\n")
            f.write(f"  - Spelling errors: {spelling_count}\n\n")
            
            f.write("Files:\n")
            for filepath in files_processed:
                f.write(f"  - {os.path.basename(filepath)}\n")
            f.write("\n")
            
            if not errors:
                f.write("-" * 80 + "\n")
                f.write("No errors found! All sentences passed grammar and spelling checks.\n")
                f.write("-" * 80 + "\n")
            else:
                # Group errors by file
                errors_by_file: dict[str, list[TextError]] = {}
                for error in errors:
                    if error.source_file not in errors_by_file:
                        errors_by_file[error.source_file] = []
                    errors_by_file[error.source_file].append(error)
                
                # Output errors grouped by file
                for filepath, file_errors in errors_by_file.items():
                    f.write("-" * 80 + "\n")
                    f.write(f"FILE: {os.path.basename(filepath)}\n")
                    f.write(f"Path: {filepath}\n")
                    f.write(f"Errors found: {len(file_errors)}\n")
                    f.write("-" * 80 + "\n\n")
                    
                    # Sort by subtitle index
                    file_errors.sort(key=lambda e: e.subtitle_index)
                    
                    for i, error in enumerate(file_errors, 1):
                        f.write(f"Error #{i}\n")
                        f.write(f"  Subtitle Index: {error.subtitle_index}\n")
                        f.write(f"  Error Type: {error.error_type.upper()}\n")
                        f.write(f"  Original Text: \"{error.original_text}\"\n")
                        f.write(f"  Error: {error.error_description}\n")
                        f.write(f"  Suggested Correction: {error.suggested_correction}\n")
                        f.write("\n")
            
            # Footer
            f.write("=" * 80 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 80 + "\n")


# ============================================================================
# GUI Application
# ============================================================================

class SRTCheckerGUI:
    """Main GUI application for SRT grammar and spelling checker."""
    
    # Model options for each provider
    GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    OPENAI_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]
    
    # Check type options
    CHECK_TYPES = ["Both (Grammar & Spelling)", "Grammar Only", "Spelling Only"]
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SRT Grammar & Spelling Checker")
        self.root.geometry("850x780")
        self.root.resizable(True, True)
        
        # Variables
        self.folder_path = tk.StringVar()
        self.llm_provider = tk.StringVar(value="Google Gemini")
        self.api_key = tk.StringVar()
        self.selected_model = tk.StringVar()
        self.check_type = tk.StringVar(value="Both (Grammar & Spelling)")
        self.files_per_batch = tk.IntVar(value=5)
        self.sentences_per_api_call = tk.IntVar(value=5)
        self.is_processing = False
        
        # Check for saved API keys in environment
        self.gemini_key = os.environ.get('GEMINI_API_KEY', '')
        self.openai_key = os.environ.get('OPENAI_API_KEY', '')
        
        # Set initial API key based on default provider
        self.api_key.set(self.gemini_key)
        self.selected_model.set(self.GEMINI_MODELS[0])
        
        self._create_widgets()
        self._check_packages()
        self._on_provider_change()  # Initialize UI based on default provider
    
    def _check_packages(self):
        """Check which packages are installed and show status."""
        missing = []
        if not NEW_GENAI_AVAILABLE and not LEGACY_GENAI_AVAILABLE:
            missing.append("Google Gemini (pip install google-genai)")
        if not OPENAI_AVAILABLE:
            missing.append("OpenAI (pip install openai)")
        
        if len(missing) == 2:
            messagebox.showwarning(
                "Missing Packages",
                "No LLM packages found.\n\n"
                "Please install at least one:\n\n"
                "For Google Gemini:\n"
                "  pip install google-genai\n\n"
                "For OpenAI:\n"
                "  pip install openai"
            )
    
    def _create_widgets(self):
        """Create all GUI widgets."""
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ===== LLM Provider Selection Section =====
        provider_frame = ttk.LabelFrame(main_frame, text="LLM Provider", padding="10")
        provider_frame.pack(fill=tk.X, pady=(0, 10))
        
        provider_inner = ttk.Frame(provider_frame)
        provider_inner.pack(fill=tk.X)
        
        # Provider selection
        ttk.Label(provider_inner, text="Select Provider:").pack(side=tk.LEFT)
        
        # Radio buttons for provider selection
        self.gemini_radio = ttk.Radiobutton(
            provider_inner, text="Google Gemini", 
            variable=self.llm_provider, value="Google Gemini",
            command=self._on_provider_change
        )
        self.gemini_radio.pack(side=tk.LEFT, padx=(15, 5))
        
        # Gemini status indicator
        gemini_available = NEW_GENAI_AVAILABLE or LEGACY_GENAI_AVAILABLE
        self.gemini_status = ttk.Label(
            provider_inner, 
            text="✓" if gemini_available else "✗",
            foreground="green" if gemini_available else "red"
        )
        self.gemini_status.pack(side=tk.LEFT, padx=(0, 20))
        
        self.openai_radio = ttk.Radiobutton(
            provider_inner, text="OpenAI", 
            variable=self.llm_provider, value="OpenAI",
            command=self._on_provider_change
        )
        self.openai_radio.pack(side=tk.LEFT, padx=(0, 5))
        
        # OpenAI status indicator
        self.openai_status = ttk.Label(
            provider_inner, 
            text="✓" if OPENAI_AVAILABLE else "✗",
            foreground="green" if OPENAI_AVAILABLE else "red"
        )
        self.openai_status.pack(side=tk.LEFT)
        
        # Model selection
        model_frame = ttk.Frame(provider_frame)
        model_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(model_frame, text="Model:").pack(side=tk.LEFT)
        self.model_combo = ttk.Combobox(
            model_frame, textvariable=self.selected_model, 
            state="readonly", width=25
        )
        self.model_combo.pack(side=tk.LEFT, padx=(10, 0))
        
        # Package install hint
        self.install_hint = ttk.Label(
            provider_frame, text="", foreground="gray", font=('Helvetica', 9)
        )
        self.install_hint.pack(anchor=tk.W, pady=(5, 0))
        
        # ===== Check Type Selection Section =====
        check_type_frame = ttk.LabelFrame(main_frame, text="Check Type", padding="10")
        check_type_frame.pack(fill=tk.X, pady=(0, 10))
        
        check_type_inner = ttk.Frame(check_type_frame)
        check_type_inner.pack(fill=tk.X)
        
        ttk.Label(check_type_inner, text="What to check:").pack(side=tk.LEFT)
        
        # Radio buttons for check type
        self.check_both_radio = ttk.Radiobutton(
            check_type_inner, text="Both (Grammar & Spelling)", 
            variable=self.check_type, value="Both (Grammar & Spelling)"
        )
        self.check_both_radio.pack(side=tk.LEFT, padx=(15, 10))
        
        self.check_grammar_radio = ttk.Radiobutton(
            check_type_inner, text="Grammar Only", 
            variable=self.check_type, value="Grammar Only"
        )
        self.check_grammar_radio.pack(side=tk.LEFT, padx=(0, 10))
        
        self.check_spelling_radio = ttk.Radiobutton(
            check_type_inner, text="Spelling Only", 
            variable=self.check_type, value="Spelling Only"
        )
        self.check_spelling_radio.pack(side=tk.LEFT)
        
        # ===== API Key Section =====
        api_frame = ttk.LabelFrame(main_frame, text="API Configuration", padding="10")
        api_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.api_key_label = ttk.Label(api_frame, text="API Key:")
        self.api_key_label.pack(anchor=tk.W)
        
        api_entry_frame = ttk.Frame(api_frame)
        api_entry_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.api_entry = ttk.Entry(api_entry_frame, textvariable=self.api_key, show="*", width=60)
        self.api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.show_key_var = tk.BooleanVar(value=False)
        self.show_key_btn = ttk.Checkbutton(
            api_entry_frame, text="Show", variable=self.show_key_var,
            command=self._toggle_key_visibility
        )
        self.show_key_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        self.api_link_label = ttk.Label(
            api_frame, text="", foreground="blue", cursor="hand2"
        )
        self.api_link_label.pack(anchor=tk.W, pady=(5, 0))
        
        # ===== Folder Selection Section =====
        folder_frame = ttk.LabelFrame(main_frame, text="SRT Files Location", padding="10")
        folder_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(folder_frame, text="Select folder containing SRT files:").pack(anchor=tk.W)
        
        folder_entry_frame = ttk.Frame(folder_frame)
        folder_entry_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.folder_entry = ttk.Entry(folder_entry_frame, textvariable=self.folder_path, width=60)
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.browse_btn = ttk.Button(folder_entry_frame, text="Browse...", command=self._browse_folder)
        self.browse_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # File count label
        self.file_count_label = ttk.Label(folder_frame, text="No folder selected")
        self.file_count_label.pack(anchor=tk.W, pady=(5, 0))
        
        # ===== Settings Section =====
        settings_frame = ttk.LabelFrame(main_frame, text="Processing Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        settings_grid = ttk.Frame(settings_frame)
        settings_grid.pack(fill=tk.X)
        
        ttk.Label(settings_grid, text="SRT files per batch:").grid(row=0, column=0, sticky=tk.W, pady=2)
        files_spinbox = ttk.Spinbox(settings_grid, from_=1, to=20, width=10,
                                     textvariable=self.files_per_batch)
        files_spinbox.grid(row=0, column=1, sticky=tk.W, padx=(10, 30), pady=2)
        
        ttk.Label(settings_grid, text="Sentences per API call:").grid(row=0, column=2, sticky=tk.W, pady=2)
        sentences_spinbox = ttk.Spinbox(settings_grid, from_=1, to=10, width=10,
                                         textvariable=self.sentences_per_api_call)
        sentences_spinbox.grid(row=0, column=3, sticky=tk.W, padx=(10, 0), pady=2)
        
        ttk.Label(settings_frame, 
                  text="Note: Processing in smaller batches helps manage API rate limits.",
                  foreground="gray").pack(anchor=tk.W, pady=(5, 0))
        
        # ===== Action Buttons Section (PROMINENT) =====
        action_frame = ttk.LabelFrame(main_frame, text="Actions", padding="15")
        action_frame.pack(fill=tk.X, pady=(0, 10))
        
        button_container = ttk.Frame(action_frame)
        button_container.pack(fill=tk.X)
        
        # Main START button - large and prominent
        self.start_btn = tk.Button(
            button_container, 
            text="▶  START CHECKING", 
            command=self._start_processing,
            font=('Helvetica', 12, 'bold'),
            bg='#4CAF50',
            fg='white',
            activebackground='#45a049',
            activeforeground='white',
            padx=20,
            pady=10,
            cursor='hand2'
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        # STOP button
        self.stop_btn = tk.Button(
            button_container, 
            text="⏹  STOP", 
            command=self._stop_processing,
            font=('Helvetica', 10, 'bold'),
            bg='#f44336',
            fg='white',
            activebackground='#da190b',
            activeforeground='white',
            padx=15,
            pady=8,
            state=tk.DISABLED,
            cursor='hand2'
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        # Open Report button
        self.open_report_btn = tk.Button(
            button_container,
            text="📄  Open Last Report",
            command=self._open_report,
            font=('Helvetica', 10),
            bg='#2196F3',
            fg='white',
            activebackground='#1976D2',
            activeforeground='white',
            padx=15,
            pady=8,
            state=tk.DISABLED,
            cursor='hand2'
        )
        self.open_report_btn.pack(side=tk.RIGHT)
        
        # Store last report path
        self.last_report_path = None
        
        # ===== Progress Section =====
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_label = ttk.Label(progress_frame, text="Ready to start")
        self.progress_label.pack(anchor=tk.W)
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=400)
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        
        self.batch_label = ttk.Label(progress_frame, text="")
        self.batch_label.pack(anchor=tk.W, pady=(5, 0))
        
        # ===== Log Section =====
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
    
    def _on_provider_change(self):
        """Handle provider selection change."""
        provider = self.llm_provider.get()
        
        if provider == "Google Gemini":
            # Update model list
            self.model_combo['values'] = self.GEMINI_MODELS
            self.selected_model.set(self.GEMINI_MODELS[0])
            
            # Update API key
            self.api_key.set(self.gemini_key)
            self.api_key_label.config(text="Google Gemini API Key:")
            self.api_link_label.config(text="Get your API key from: https://aistudio.google.com/app/apikey")
            
            # Update install hint
            if not NEW_GENAI_AVAILABLE and not LEGACY_GENAI_AVAILABLE:
                self.install_hint.config(text="⚠ Package not installed. Run: pip install google-genai")
            else:
                self.install_hint.config(text="✓ Package installed and ready")
        
        elif provider == "OpenAI":
            # Update model list
            self.model_combo['values'] = self.OPENAI_MODELS
            self.selected_model.set(self.OPENAI_MODELS[0])
            
            # Update API key
            self.api_key.set(self.openai_key)
            self.api_key_label.config(text="OpenAI API Key:")
            self.api_link_label.config(text="Get your API key from: https://platform.openai.com/api-keys")
            
            # Update install hint
            if not OPENAI_AVAILABLE:
                self.install_hint.config(text="⚠ Package not installed. Run: pip install openai")
            else:
                self.install_hint.config(text="✓ Package installed and ready")
    
    def _toggle_key_visibility(self):
        """Toggle API key visibility."""
        if self.show_key_var.get():
            self.api_entry.config(show="")
        else:
            self.api_entry.config(show="*")
    
    def _browse_folder(self):
        """Open folder browser dialog."""
        folder = filedialog.askdirectory(title="Select Folder Containing SRT Files")
        if folder:
            self.folder_path.set(folder)
            self._update_file_count()
    
    def _update_file_count(self):
        """Update the file count label."""
        folder = self.folder_path.get()
        if folder and os.path.isdir(folder):
            srt_files = list(Path(folder).glob('**/*.srt'))
            count = len(srt_files)
            self.file_count_label.config(
                text=f"Found {count} SRT file(s)" if count > 0 else "No SRT files found in this folder"
            )
        else:
            self.file_count_label.config(text="No folder selected")
    
    def _log(self, message: str):
        """Add message to log."""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _start_processing(self):
        """Start the processing in a separate thread."""
        provider = self.llm_provider.get()
        
        # Check if package is available
        if provider == "Google Gemini" and not NEW_GENAI_AVAILABLE and not LEGACY_GENAI_AVAILABLE:
            messagebox.showerror("Error", "Google Gemini package not installed.\n\nInstall with: pip install google-genai")
            return
        
        if provider == "OpenAI" and not OPENAI_AVAILABLE:
            messagebox.showerror("Error", "OpenAI package not installed.\n\nInstall with: pip install openai")
            return
        
        # Validate inputs
        if not self.api_key.get().strip():
            messagebox.showerror("Error", f"Please enter your {provider} API key.")
            return
        
        if not self.folder_path.get().strip():
            messagebox.showerror("Error", "Please select a folder containing SRT files.")
            return
        
        folder = self.folder_path.get()
        if not os.path.isdir(folder):
            messagebox.showerror("Error", "Selected folder does not exist.")
            return
        
        srt_files = list(Path(folder).glob('**/*.srt'))
        if not srt_files:
            messagebox.showerror("Error", "No SRT files found in the selected folder.")
            return
        
        # Save the current API key for the provider
        if provider == "Google Gemini":
            self.gemini_key = self.api_key.get().strip()
        else:
            self.openai_key = self.api_key.get().strip()
        
        # Update UI state
        self.is_processing = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.browse_btn.config(state=tk.DISABLED)
        self.gemini_radio.config(state=tk.DISABLED)
        self.openai_radio.config(state=tk.DISABLED)
        self.model_combo.config(state=tk.DISABLED)
        self.check_both_radio.config(state=tk.DISABLED)
        self.check_grammar_radio.config(state=tk.DISABLED)
        self.check_spelling_radio.config(state=tk.DISABLED)
        
        # Clear log
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # Start processing thread
        thread = threading.Thread(target=self._process_files, args=(srt_files,))
        thread.daemon = True
        thread.start()
    
    def _stop_processing(self):
        """Stop the processing."""
        self.is_processing = False
        self._log("Stopping... Will complete current batch.")
    
    def _process_files(self, srt_files: list[Path]):
        """Process SRT files in batches."""
        provider = self.llm_provider.get()
        model_name = self.selected_model.get()
        check_type_display = self.check_type.get()
        
        # Convert display check type to internal format
        if "Grammar Only" in check_type_display:
            check_type_internal = "grammar"
        elif "Spelling Only" in check_type_display:
            check_type_internal = "spelling"
        else:
            check_type_internal = "both"
        
        try:
            # Initialize components
            srt_parser = SRTParser()
            sentence_extractor = SentenceExtractor()
            report_generator = ReportGenerator()
            
            # Create appropriate checker
            self._log(f"Initializing {provider} with model: {model_name}")
            self._log(f"Check type: {check_type_display}")
            
            if provider == "Google Gemini":
                checker = GeminiChecker(self.api_key.get().strip(), model_name)
            else:
                checker = OpenAIChecker(self.api_key.get().strip(), model_name)
            
            # Set the check type
            checker.set_check_type(check_type_internal)
            
            files_per_batch = self.files_per_batch.get()
            sentences_per_call = self.sentences_per_api_call.get()
            
            all_errors = []
            all_sentences = []
            processed_files = []
            
            total_files = len(srt_files)
            total_batches = (total_files + files_per_batch - 1) // files_per_batch
            
            self._log(f"Starting to process {total_files} SRT file(s) in {total_batches} batch(es)")
            
            for batch_num in range(total_batches):
                if not self.is_processing:
                    self._log("Processing stopped by user.")
                    break
                
                start_idx = batch_num * files_per_batch
                end_idx = min(start_idx + files_per_batch, total_files)
                batch_files = srt_files[start_idx:end_idx]
                
                self.root.after(0, lambda b=batch_num+1, t=total_batches: 
                               self.batch_label.config(text=f"Processing batch {b} of {t}"))
                self._log(f"\n--- Batch {batch_num + 1}/{total_batches} ---")
                
                for filepath in batch_files:
                    if not self.is_processing:
                        break
                    
                    filename = os.path.basename(filepath)
                    self._log(f"Processing: {filename}")
                    
                    try:
                        # Parse SRT file
                        entries = srt_parser.parse_file(str(filepath))
                        self._log(f"  Parsed {len(entries)} subtitle entries")
                        
                        # Extract sentences
                        sentences = sentence_extractor.extract_sentences(entries, str(filepath))
                        self._log(f"  Extracted {len(sentences)} sentences")
                        all_sentences.extend(sentences)
                        
                        # Check grammar and spelling
                        if sentences:
                            def progress_callback(current, total):
                                progress = (current / total) * 100
                                self.root.after(0, lambda p=progress: self.progress_bar.config(value=p))
                            
                            errors = checker.check_sentences_batch(
                                sentences, sentences_per_call, progress_callback
                            )
                            all_errors.extend(errors)
                            self._log(f"  Found {len(errors)} error(s)")
                        
                        processed_files.append(str(filepath))
                        
                    except Exception as e:
                        self._log(f"  Error: {str(e)}")
                
                # Update overall progress
                overall_progress = ((batch_num + 1) / total_batches) * 100
                self.root.after(0, lambda p=overall_progress: self.progress_bar.config(value=p))
            
            # Generate report
            if processed_files:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_filename = f"grammar_spelling_report_{timestamp}.txt"
                report_path = os.path.join(self.folder_path.get(), report_filename)
                
                report_generator.generate_report(
                    all_errors, report_path, processed_files, len(all_sentences),
                    llm_provider=provider, model_name=model_name, check_type=check_type_display
                )
                
                self.last_report_path = report_path
                self.root.after(0, lambda: self.open_report_btn.config(state=tk.NORMAL))
                
                self._log(f"\n{'='*50}")
                self._log(f"COMPLETED!")
                self._log(f"Provider: {provider} ({model_name})")
                self._log(f"Check type: {check_type_display}")
                self._log(f"Files processed: {len(processed_files)}")
                self._log(f"Sentences checked: {len(all_sentences)}")
                self._log(f"Errors found: {len(all_errors)}")
                self._log(f"Report saved: {report_filename}")
                self._log(f"{'='*50}")
                
                # Show completion message
                self.root.after(0, lambda: messagebox.showinfo(
                    "Complete",
                    f"Processing complete!\n\n"
                    f"Provider: {provider}\n"
                    f"Model: {model_name}\n"
                    f"Check type: {check_type_display}\n"
                    f"Files processed: {len(processed_files)}\n"
                    f"Sentences checked: {len(all_sentences)}\n"
                    f"Errors found: {len(all_errors)}\n\n"
                    f"Report saved to:\n{report_path}"
                ))
            
        except Exception as e:
            self._log(f"Error: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"An error occurred:\n{str(e)}"))
        
        finally:
            # Reset UI state
            self.is_processing = False
            self.root.after(0, self._reset_ui)
    
    def _reset_ui(self):
        """Reset UI to ready state."""
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.browse_btn.config(state=tk.NORMAL)
        self.gemini_radio.config(state=tk.NORMAL)
        self.openai_radio.config(state=tk.NORMAL)
        self.model_combo.config(state="readonly")
        self.check_both_radio.config(state=tk.NORMAL)
        self.check_grammar_radio.config(state=tk.NORMAL)
        self.check_spelling_radio.config(state=tk.NORMAL)
        self.progress_label.config(text="Ready")
        self.batch_label.config(text="")
    
    def _open_report(self):
        """Open the last generated report."""
        if self.last_report_path and os.path.exists(self.last_report_path):
            if sys.platform == 'win32':
                os.startfile(self.last_report_path)
            elif sys.platform == 'darwin':
                os.system(f'open "{self.last_report_path}"')
            else:
                os.system(f'xdg-open "{self.last_report_path}"')
    
    def run(self):
        """Start the GUI application."""
        self.root.mainloop()


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point."""
    app = SRTCheckerGUI()
    app.run()


if __name__ == '__main__':
    main()
