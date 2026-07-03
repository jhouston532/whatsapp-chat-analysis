import re
import csv
import argparse
import os
from datetime import datetime
from collections import Counter
import string

def parse_whatsapp_chat(filepath):
    """
    Reads the WhatsApp chat file and parses the date, time, sender, and message.
    Skips malformed lines or system messages that don't follow the standard user message format.
    """
    parsed_messages = []
    # Regex to capture [MM/DD/YY, HH:MM:SS AM/PM] Sender: Message
    pattern = re.compile(r'^\[(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s(?P<time>\d{1,2}:\d{2}:\d{2}\s[AP]M)\]\s(?P<sender>[^:]+):\s(?P<message>.*)$')

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.match(line.strip())
            if match:
                date_str = match.group('date')
                time_str = match.group('time')
                datetime_str = f"{date_str} {time_str}"
                
                try:
                    # Convert the string into a datetime object for mathematical operations
                    dt_obj = datetime.strptime(datetime_str, "%m/%d/%y %I:%M:%S %p")
                except ValueError:
                    continue # Skip lines with unexpected date formats

                parsed_messages.append({
                    'datetime': dt_obj,
                    'time_only': dt_obj.time(),
                    'sender': match.group('sender').strip(),
                    'message': match.group('message').strip()
                })
                
    return parsed_messages

def export_user_times(messages, output_dir):
    """
    Exports a CSV tracking the exact time of day each user sent a message.
    Useful for creating scatter plots of user activity over the day.
    """
    output_file = os.path.join(output_dir, 'user_message_times.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Sender', 'Date', 'TimeOfDay', 'Hour_of_Day'])
        for msg in messages:
            writer.writerow([
                msg['sender'],
                msg['datetime'].date(),
                msg['time_only'],
                msg['datetime'].hour # Extracting the hour makes bar chart aggregations easier
            ])

def analyze_message_chains(messages, output_dir):
    """
    Calculates the time elapsed (in seconds) between consecutive messages in the chat.
    This tracks behavioral patterns to help identify bots programmed with set delay intervals.
    """
    output_file = os.path.join(output_dir, 'message_chain_intervals.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Current_Sender', 'Previous_Sender', 'Time_Delta_Seconds', 'Timestamp'])

        # Start from the second message to compare it against the first
        for i in range(1, len(messages)):
            current_msg = messages[i]
            prev_msg = messages[i-1]

            # Calculate exact wait time between this message and the preceding one
            delta = current_msg['datetime'] - prev_msg['datetime']
            delta_seconds = delta.total_seconds()

            writer.writerow([
                current_msg['sender'],
                prev_msg['sender'],
                delta_seconds,
                current_msg['datetime']
            ])

def export_keyword_popularity(messages, output_dir):
    """
    Generates a separate CSV for each user detailing their most frequently used keywords,
    filtering out common punctuation and stop words.
    """
    user_messages = {}
    # Basic filter to remove conversational noise
    stop_words = {'the', 'and', 'to', 'a', 'of', 'in', 'is', 'it', 'you', 'that', 'this', 'for', 'on', 'with', 'as', 'i', 'my', 'are', 'but', 'not', 'we', 'they', 'have', 'be', 'your', 'can'}

    # Group all message text by the sender
    for msg in messages:
        sender = msg['sender']
        if sender not in user_messages:
            user_messages[sender] = []
        user_messages[sender].append(msg['message'])

    # Create a sub-folder to keep the workspace clean
    keywords_dir = os.path.join(output_dir, 'user_keywords')
    os.makedirs(keywords_dir, exist_ok=True)

    for sender, msgs in user_messages.items():
        words = []
        for text in msgs:
            # Strip punctuation and lower the case for accurate counting
            clean_text = text.translate(str.maketrans('', '', string.punctuation)).lower()
            words.extend([w for w in clean_text.split() if w not in stop_words and w.strip()])

        word_counts = Counter(words)

        # Remove special characters from the sender's name so it can be used as a valid file name
        safe_sender = re.sub(r'[\\/*?:"<>|~]', "", sender).strip()
        output_file = os.path.join(keywords_dir, f"{safe_sender}_keywords.csv")

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Keyword', 'Frequency'])
            for word, count in word_counts.most_common():
                writer.writerow([word, count])

def main():
    # Setup command line argument parsing
    parser = argparse.ArgumentParser(description="Analyze a WhatsApp chat export for behavioral metrics.")
    parser.add_argument("filepath", help="Path to the WhatsApp .txt file")
    args = parser.parse_args()

    if not os.path.exists(args.filepath):
        print(f"Error: File '{args.filepath}' not found.")
        return

    print(f"Parsing {args.filepath}...")
    messages = parse_whatsapp_chat(args.filepath)

    if not messages:
        print("No messages parsed. Please check that the file follows the expected format.")
        return

    # Create a dedicated directory for the outputs based on the input filename
    base_name = os.path.splitext(os.path.basename(args.filepath))[0]
    output_dir = f"{base_name}_analysis"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Found {len(messages)} valid messages. Generating reports in '{output_dir}/'...")

    # Execute the individual analysis functions
    export_user_times(messages, output_dir)
    analyze_message_chains(messages, output_dir)
    export_keyword_popularity(messages, output_dir)

    print("Analysis complete. Check the output directory for your CSV files.")

if __name__ == "__main__":
    main()