```text
# WhatsApp Chat Analysis Tool
## Software Architecture and Agentic Development Plan

---

# Project Goal

Develop a modular Python tool that analyzes exported WhatsApp group chats for behavioral, temporal, and linguistic patterns, particularly those useful for detecting coordinated or potentially automated activity.

The program should:

- Accept a WhatsApp exported `.txt` file as input.
- Parse the chat into structured message objects.
- Perform multiple independent analyses.
- Save each analysis as one or more CSV files.
- Produce outputs that are easy to visualize using Excel, LibreOffice, pandas, matplotlib, Tableau, Power BI, R, or similar tools.
- Use only the Python Standard Library unless otherwise specified.
- Be heavily commented.
- Be organized into small, focused functions with a single responsibility.
- Be easily extendable.

The entire project should be organized into independent modules that communicate only through a shared data model.

---

# Overall Architecture

whatsapp_analysis/

    script.py

    parser.py
    message.py

    timeline.py
    bursts.py
    keywords.py
    statistics.py
    correlations.py

    csv_writer.py
    tokenizer.py
    stopwords.py
    utils.py

    config.py

    tests/

    README.md

Each module should have exactly one responsibility.

No module should depend on another analysis module.

All communication should occur through Message objects.

---

# Core Data Model

Everything revolves around one object.

Message

Fields:

timestamp : datetime

date : date

time : time

year

month

day

weekday

hour

minute

second

timezone

author

raw_author

message

message_length

is_system_message

is_media

line_number

Every analysis module accepts:

list[Message]

and returns analysis results.

No analysis module should read files directly.

No analysis module should parse raw text.

---

# Agent 1

## message.py

Goal:

Create the Message data model.

Responsibilities:

- Define the Message dataclass.
- No logic.
- No parsing.
- No analysis.

Deliverable:

message.py

---

# Agent 2

## parser.py

Goal:

Read exported WhatsApp chats and convert them into Message objects.

Input:

chat.txt

Output:

list[Message]

Functions:

load_file(filepath)

split_into_records(lines)

parse_record(record)

parse_timestamp(text)

parse_author(text)

parse_message(text)

is_system_message(author, message)

is_media_message(message)

clean_author(author)

validate_record(record)

parse_chat(filepath)

Requirements:

Must support:

- Multi-line messages
- UTF-8 encoding
- Emojis
- Unicode
- Phone numbers
- Display names
- Group notifications
- Join events
- Leave events
- Edited messages
- Deleted messages
- Media placeholders
- Empty messages
- Malformed records (gracefully)

Deliverable:

parser.py

---

# Agent 3

## timeline.py

Goal:

Produce chronological activity reports.

Functions:

message_timeline(messages)

hourly_activity(messages)

daily_activity(messages)

weekly_activity(messages)

monthly_activity(messages)

per_user_activity(messages)

conversation_timeline(messages)

Outputs:

timeline.csv

hourly.csv

daily.csv

weekly.csv

monthly.csv

user_activity.csv

---

# Agent 4

## bursts.py

Goal:

Detect clusters ("bursts") of activity.

Functions:

compute_time_gaps(messages)

detect_bursts(messages)

burst_statistics(bursts)

assign_burst_ids(messages)

burst_summary(messages)

Parameters:

maximum_gap_seconds

minimum_messages

rolling_window

Outputs:

bursts.csv

burst_messages.csv

gaps.csv

---

# Agent 5

## tokenizer.py

Goal:

Convert messages into normalized word tokens.

Functions:

normalize_text()

remove_urls()

remove_phone_numbers()

remove_emails()

remove_emojis()

remove_punctuation()

remove_numbers()

tokenize()

remove_stopwords()

stem_word()

count_words()

No CSV writing.

No statistics.

Only token processing.

---

# Agent 6

## keywords.py

Input:

list[Message]

Functions:

overall_keywords()

user_keywords()

keyword_matrix()

keyword_percentages()

term_frequency()

inverse_document_frequency()

tfidf()

vocabulary_size()

top_keywords()

Outputs:

overall_keywords.csv

keywords/

    User1.csv
    User2.csv
    ...

---

# Agent 7

## statistics.py

Goal:

General descriptive statistics.

Functions:

messages_per_user()

average_message_length()

median_message_length()

minimum_message_length()

maximum_message_length()

conversation_duration()

first_last_message()

messages_per_hour()

messages_per_day()

messages_per_week()

message_length_distribution()

Outputs:

statistics.csv

users.csv

---

# Agent 8

## correlations.py

Goal:

Analyze interactions between users.

Functions:

response_times()

pairwise_response_times()

cross_correlation()

conversation_graph()

adjacency_matrix()

transition_matrix()

alternating_patterns()

Outputs:

response_times.csv

pairwise.csv

adjacency.csv

transitions.csv

---

# Agent 9

## csv_writer.py

Goal:

Centralized CSV writing.

Functions:

ensure_directory()

write_csv()

write_dictionary()

write_table()

sanitize_filename()

timestamp_filename()

Responsibilities:

Only write CSV files.

No parsing.

No analysis.

---

# Agent 10

## utils.py

Functions:

parse_datetime()

safe_filename()

percent()

mean()

median()

rolling_average()

flatten()

slugify()

seconds_between()

group_by()

Reusable helper functions only.

---

# Agent 11

## config.py

Contains configuration constants only.

STOPWORDS

BURST_THRESHOLD

MIN_BURST_MESSAGES

TIMEZONE

CSV_DELIMITER

OUTPUT_FOLDER

KEYWORD_LIMIT

No logic.

---

# Agent 12

## script.py

Goal:

Main entry point.

Functions:

main()

parse_arguments()

run_pipeline()

print_summary()

Pipeline:

Input Chat

↓

Parser

↓

Message Objects

↓

Timeline

↓

Bursts

↓

Keywords

↓

Statistics

↓

Correlations

↓

CSV Writer

---

# Additional Analysis Modules

These analyses are recommended because they provide useful signals for detecting coordinated or automated behavior.

---

# Agent 13

## Conversation Graph

Goal:

Generate interaction graphs.

Outputs:

reply_graph.csv

nodes.csv

edges.csv

Definition:

If User B posts immediately after User A,

Create an edge:

A → B

Useful for visualization in:

- Gephi
- Cytoscape
- NetworkX

---

# Agent 14

## Timing Fingerprints

Goal:

Measure posting rhythm.

Functions:

user_intervals()

mean_interval()

median_interval()

stddev_interval()

histogram()

Outputs:

timing_profiles.csv

Bots frequently exhibit much lower variance in posting intervals than humans.

---

# Agent 15

## Vocabulary Richness

Goal:

Measure lexical diversity.

Functions:

type_token_ratio()

hapax_legomena()

average_word_length()

unique_words()

repeated_phrases()

Outputs:

vocabulary.csv

Bots often reuse a constrained vocabulary.

---

# Agent 16

## Phrase Mining

Goal:

Identify repeated phrases.

Functions:

bigrams()

trigrams()

repeated_sequences()

common_sentences()

Outputs:

bigrams.csv

trigrams.csv

phrases.csv

---

# Agent 17

## Similarity Analysis

Goal:

Compare messages across users.

Functions:

cosine_similarity()

jaccard_similarity()

message_similarity()

duplicate_messages()

Outputs:

similarity.csv

duplicates.csv

Highly similar messaging across multiple users can indicate coordinated activity.

---

# Testing Agent

One independent agent should write tests only.

Expected tests:

Parser

✓ Multi-line messages

✓ Unicode

✓ Emojis

✓ Phone numbers

✓ Media messages

✓ Deleted messages

✓ Edited messages

✓ Join events

✓ Leave events

✓ Malformed records

Timeline

✓ Hour counts

✓ Day counts

✓ Weekly counts

✓ Monthly counts

Bursts

✓ Burst detection

✓ Boundary conditions

✓ Empty chats

Tokenizer

✓ Punctuation removal

✓ URL removal

✓ Phone number removal

✓ Stopword removal

✓ Tokenization

Keywords

✓ Word counting

✓ TF

✓ IDF

✓ TF-IDF

Statistics

✓ Mean

✓ Median

✓ Distribution

CSV Writer

✓ File creation

✓ Correct CSV formatting

✓ Filename sanitization

---

# Dependency Graph

script.py
│
├── parser.py
│
│   ↓
│
│ Message Objects
│
├── timeline.py
├── bursts.py
├── keywords.py
├── statistics.py
├── correlations.py
│
├── tokenizer.py
├── stopwords.py
├── utils.py
│
└── csv_writer.py

The Message data model is the central interface between all analysis modules.

No analysis module should call another analysis module directly.

All modules should be independently testable.

All outputs should be deterministic given identical input.

Every function should have:

- A single responsibility.
- Clear docstrings.
- Type hints.
- Defensive error checking.
- Small size (preferably under 30 lines where practical).
- Unit tests.

The final system should be easy to extend with future analyses such as:

- Bot likelihood scoring
- Sentiment analysis
- Community detection
- Topic modeling
- Named entity extraction
- Network centrality metrics
- Temporal clustering
- Interactive dashboards
- Machine learning classifiers
- Research-specific behavioral metrics
```
