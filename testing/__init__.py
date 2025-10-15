from datetime import datetime, UTC

from config import Paths


def log_testing_mode(output_text, title=None, metadata=None):
    """
    Append dry-run or testing-mode output to a markdown log file.

    Args:
        output_text (str): The body of the message or reply.
        title (str, optional): Section title to display as a Markdown heading.
        metadata (dict, optional): Key-value pairs to log before the content.
    """
    filepath = Paths.LOGS['TESTING']
    timestamp = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S %Z')
    with open(filepath, "a", encoding="utf-8") as f:
        f.write("\n---\n")  # Markdown horizontal rule
        f.write(f"### {title or 'Testing Mode Log'}\n")
        f.write(f"*Timestamp:* {timestamp}\n")

        if metadata:
            for key, value in metadata.items():
                f.write(f"\n*{key}:* {value}")

        f.write("\n\n```\n")
        f.write(output_text.strip())
        f.write("\n```\n")
