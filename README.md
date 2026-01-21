# SRT Grammar & Spelling Checker

A Python GUI application that checks grammar AND/OR spelling in SRT subtitle files using either **Google Gemini** or **OpenAI** APIs.

## Features

- **Dual LLM Support**: Choose between Google Gemini or OpenAI as your LLM provider
- **Model Selection**: Pick from multiple models for each provider
- **Flexible Check Types**: Choose to check Grammar Only, Spelling Only, or Both
- **GUI Interface**: Easy-to-use graphical interface with folder browser
- **API Key Input**: Secure input field for your API key (remembers keys for both providers)
- **Batch Processing**: Process SRT files in configurable batches (default: 5 files per batch)
- **Sentence Extraction**: Extracts complete sentences based on punctuation
- **Index Tracking**: Labels each error by the subtitle index where it occurs
- **Detailed Reports**: Generates comprehensive error reports in TXT format
- **Progress Tracking**: Real-time progress display with logging

## Supported LLM Providers

| Provider | Models | Install Command |
|----------|--------|-----------------|
| **Google Gemini** | gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro | `pip install google-genai` |
| **OpenAI** | gpt-4o-mini, gpt-4o, gpt-4-turbo, gpt-4, gpt-3.5-turbo | `pip install openai` |

## Installation

### 1. Install Python 3.10+ (if not already installed)

### 2. Install at least one LLM package

**For Google Gemini:**
```bash
pip install google-genai
```

**For OpenAI:**
```bash
pip install openai
```

**Or install both:**
```bash
pip install google-genai openai
```

### 3. Get an API key

**Google Gemini:**
- Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
- Create a new API key

**OpenAI:**
- Go to [OpenAI Platform](https://platform.openai.com/api-keys)
- Create a new API key

## Usage

### Running the GUI Application

```bash
python srt_grammar_checker_gui.py
```

### Using the GUI

1. **Select LLM Provider**: Choose between "Google Gemini" or "OpenAI"
   - A ✓ or ✗ indicator shows if the package is installed
2. **Select Model**: Pick from available models for the selected provider
3. **Select Check Type**: Choose what to check:
   - **Both (Grammar & Spelling)**: Check for all errors (default)
   - **Grammar Only**: Check only for grammar issues
   - **Spelling Only**: Check only for spelling mistakes
4. **Enter API Key**: Paste your API key (the app remembers keys for both providers)
5. **Select Folder**: Click "Browse..." to select the folder containing your SRT files
6. **Configure Settings** (optional):
   - **SRT files per batch**: How many SRT files to process before pausing (default: 5)
   - **Sentences per API call**: How many sentences to send in each API request (default: 5)
7. **Start Processing**: Click the green "▶ START CHECKING" button
8. **View Report**: Once complete, click "📄 Open Last Report" to view the results

### GUI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  LLM Provider                                                   │
│  Select Provider: ◉ Google Gemini ✓   ○ OpenAI ✓              │
│  Model: [gemini-2.0-flash     ▼]                               │
│  ✓ Package installed and ready                                 │
├─────────────────────────────────────────────────────────────────┤
│  Check Type                                                     │
│  What to check: ◉ Both (Grammar & Spelling)                    │
│                 ○ Grammar Only   ○ Spelling Only               │
├─────────────────────────────────────────────────────────────────┤
│  API Configuration                                              │
│  Google Gemini API Key:                                         │
│  [●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●] ☐ Show               │
│  Get your API key from: https://aistudio.google.com/app/apikey │
├─────────────────────────────────────────────────────────────────┤
│  SRT Files Location                                             │
│  [C:\Users\Me\Subtitles                    ] [Browse...]       │
│  Found 23 SRT file(s)                                           │
├─────────────────────────────────────────────────────────────────┤
│  Processing Settings                                            │
│  SRT files per batch: [5]    Sentences per API call: [5]       │
├─────────────────────────────────────────────────────────────────┤
│  Actions                                                        │
│  [▶ START CHECKING]  [⏹ STOP]              [📄 Open Report]    │
├─────────────────────────────────────────────────────────────────┤
│  Progress                                                       │
│  [████████████████████░░░░░░░░░░░░░░░░░░░░] 45%                │
│  Processing batch 2 of 5                                        │
├─────────────────────────────────────────────────────────────────┤
│  Log                                                            │
│  [10:30:45] Initializing Google Gemini with model: gemini-2.0  │
│  [10:30:45] Check type: Both (Grammar & Spelling)              │
│  [10:30:46] Processing: movie_part1.srt                        │
│  [10:30:48]   Found 3 error(s)                                 │
└─────────────────────────────────────────────────────────────────┘
```

## How It Works

### 1. SRT Parsing
The program reads SRT files and extracts subtitle entries, removing HTML/formatting tags.

### 2. Sentence Extraction
Sentences are identified by ending punctuation (`. ! ?`). Text spanning multiple subtitle entries is combined into complete sentences.

### 3. Check Type Selection
Choose what type of errors to look for:

| Check Type | What It Finds |
|------------|---------------|
| **Both (Grammar & Spelling)** | All grammar and spelling errors |
| **Grammar Only** | Subject-verb agreement, tense issues, punctuation, word choice, missing words, incorrect plurals, article usage |
| **Spelling Only** | Misspelled words, typos, incorrect word forms, commonly confused words |

### 4. AI-Powered Checking
Sentences are sent to your chosen LLM provider in batches. The AI analyzes each sentence based on your selected check type.

### 5. Report Generation
The report includes:
- LLM provider, model, and check type used
- Summary statistics (total files, sentences, errors by type)
- Detailed error entries with subtitle index, error type, and suggested correction

## Sample Output

```
================================================================================
SRT GRAMMAR & SPELLING CHECK ERROR REPORT
================================================================================

Generated: 2025-01-19 10:30:45
LLM Provider: OpenAI
Model: gpt-4o-mini
Check Type: Both (Grammar & Spelling)
Files processed: 5
Total sentences checked: 234
Total errors found: 12
  - Grammar errors: 8
  - Spelling errors: 4

Files:
  - movie_part1.srt
  - movie_part2.srt
  ...

--------------------------------------------------------------------------------
FILE: movie_part1.srt
Errors found: 3
--------------------------------------------------------------------------------

Error #1
  Subtitle Index: 2
  Error Type: BOTH
  Original Text: "I wants to show you somthing very important."
  Error: Grammar: "wants" should be "want". Spelling: "somthing" → "something"
  Suggested Correction: I want to show you something very important.

================================================================================
END OF REPORT
================================================================================
```

## Environment Variables (Optional)

You can set API keys as environment variables to pre-fill them in the GUI:

```bash
# For Google Gemini
export GEMINI_API_KEY="your-gemini-key"

# For OpenAI
export OPENAI_API_KEY="your-openai-key"
```

## Tips

1. **Model Selection**:
   - **Gemini**: `gemini-2.0-flash` is fast and cost-effective
   - **OpenAI**: `gpt-4o-mini` offers good balance of speed and accuracy

2. **Batch Size**: Smaller batches (3-5) give more accurate results

3. **Cost Considerations**: 
   - OpenAI charges per token; larger files = higher cost
   - Gemini offers generous free tiers

4. **False Positives**: The AI may flag intentional informal speech in dialogue

## Troubleshooting

**"Package not installed" indicator (✗)**
- Install the required package for your chosen provider

**API errors**
- Verify your API key is correct
- Check you have sufficient API credits/quota

**Rate limit errors**
- Reduce "Sentences per API call" to 3
- Process fewer files per batch

## Files Included

```
srt_grammar_checker_gui.py   # Main GUI application
sample_subtitles.srt         # Example SRT with errors for testing
README.md                    # This file
```

## License

MIT License - Feel free to modify and use as needed.
