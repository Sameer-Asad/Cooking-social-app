# Dastarkhwan eval suite

Excludes Operations (no golden dataset — that's load-testing, not eval).

## Setup (one time)

```bash
pip install deepeval jiwer pytest litellm
```

`.env`:
```
GROQ_API_KEY=your_groq_key
LITELLM_API_KEY=your_groq_key
USE_LITELLM=1
```

```bash
deepeval set-litellm --model=groq/llama-3.3-70b-versatile --save
```

Confirm ffmpeg is on PATH (needed for the STT harness):
```bash
ffmpeg -version
```

## Folder structure

```
eval/
├── config.yaml              # category -> metrics -> native/custom mapping
├── generate_datasets.py     # regenerates all golden_datasets/*.jsonl
├── golden_datasets/
│   ├── retriever.jsonl      (20)
│   ├── generator.jsonl      (20)
│   ├── agent.jsonl          (20)
│   ├── safety.jsonl         (20)
│   ├── multi_turn.jsonl     (20)
│   ├── stt/
│   │   ├── audio/           # <- add your own .wav/.webm clips here
│   │   └── transcripts.jsonl (10)
│   └── tts/
│       └── markdown_samples.jsonl (20)
├── harness/
│   ├── common/
│   │   ├── metrics.py       # all deterministic/jiwer custom metrics
│   │   └── custom_geval.py  # all custom G-Eval (LLM-judged) metrics
│   ├── run_retriever_eval.py
│   ├── run_generator_eval.py
│   ├── run_agent_eval.py
│   ├── run_safety_eval.py
│   ├── run_multi_turn_eval.py
│   ├── run_stt_eval.py
│   └── run_tts_eval.py
└── results/                 # JSON output per run, timestamped
```

## ⚠️ Before running the STT harness

`golden_datasets/stt/transcripts.jsonl` references 10 audio files under
`golden_datasets/stt/audio/` that **do not exist yet** — I generated the
ground-truth text and language labels, but actual audio recording
requires a human voice (or TTS-generated placeholder audio you make
yourself). Record or synthesize 10 clips matching the `audio_path` /
`ground_truth_text` / `language` fields in that file before running
`run_stt_eval.py`, or it will fail on missing files.

## Running a category

```bash
cd backend
python -m eval.harness.run_agent_eval
```

Each script prints per-metric scores plus writes a timestamped JSON
report to `eval/results/`.
