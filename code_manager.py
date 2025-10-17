import pandas as pd
from pathlib import Path

from config import Paths

# Location of our main ISO dataset for codes
CSV_PATH = Path(Paths.DATASETS['ISO_CODES'])


def load_csv():
    """Load the CSV file and return as DataFrame."""
    try:
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        df = None
        for encoding in encodings:
            try:
                df = pd.read_csv(CSV_PATH, encoding=encoding)
                return df
            except (UnicodeDecodeError, UnicodeError):
                continue

        if df is None:
            print(f"Error: Could not decode file with any standard encoding.")
            return None
    except FileNotFoundError:
        print(f"Error: File not found at {CSV_PATH}")
        return None


def save_csv(df):
    """Save DataFrame back to CSV file."""
    try:
        df.to_csv(CSV_PATH, index=False, encoding='utf-8')
        print("✓ File saved successfully.")
    except Exception as e:
        print(f"Error saving file: {e}")


def create_entry():
    """Create a new ISO 639-3 entry."""
    df = load_csv()
    if df is None:
        return

    iso_639_3 = input("Enter ISO 639-3 code: ").strip()

    # Check if code already exists
    if iso_639_3 in df['ISO 639-3'].values:
        print(f"Error: ISO 639-3 code '{iso_639_3}' already exists.")
        return

    language_name = input("Enter Language Name: ").strip()

    if not iso_639_3 or not language_name:
        print("Error: ISO 639-3 and Language Name cannot be empty.")
        return

    # Create new row with empty ISO 639-1 and Alternate Names
    new_row = {
        'ISO 639-3': iso_639_3,
        'ISO 639-1': '',
        'Language Name': language_name,
        'Alternate Names': ''
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_csv(df)
    print(f"✓ Created new entry: {iso_639_3} - {language_name}")


def update_entry():
    """Update the Language Name for an existing ISO 639-3 code."""
    df = load_csv()
    if df is None:
        return

    iso_639_3 = input("Enter ISO 639-3 code to update: ").strip()

    if iso_639_3 not in df['ISO 639-3'].values:
        print(f"Error: ISO 639-3 code '{iso_639_3}' not found.")
        return

    current_name = df[df['ISO 639-3'] == iso_639_3]['Language Name'].values[0]
    print(f"Current Language Name: {current_name}")

    new_name = input("Enter updated Language Name: ").strip()

    if not new_name:
        print("Error: Language Name cannot be empty.")
        return

    df.loc[df['ISO 639-3'] == iso_639_3, 'Language Name'] = new_name
    save_csv(df)
    print(f"✓ Updated {iso_639_3}: {current_name} → {new_name}")


def deprecate_entry():
    """Remove a row with the specified ISO 639-3 code."""
    df = load_csv()
    if df is None:
        return

    iso_639_3 = input("Enter ISO 639-3 code to deprecate: ").strip()

    if iso_639_3 not in df["ISO 639-3"].values:
        print(f"Error: ISO 639-3 code '{iso_639_3}' not found.")
        return

    language_name = df[df["ISO 639-3"] == iso_639_3]["Language Name"].values[0]
    confirm = (
        input(
            f"Are you sure you want to delete '{iso_639_3} - {language_name}'? (yes/no): "
        )
        .strip()
        .lower()
    )

    if confirm != "yes":
        print("Cancelled.")
        return

    df = df[df["ISO 639-3"] != iso_639_3]
    save_csv(df)
    print(f"✓ Deprecated {iso_639_3} - {language_name}")


def main():
    """Main menu loop."""
    while True:
        print("\n--- ISO Codes Manager ---")
        print("1. Create new entry")
        print("2. Update entry")
        print("3. Deprecate entry")
        print("4. Exit")

        choice = input("\nSelect operation (1-4): ").strip()

        if choice == "1":
            create_entry()
        elif choice == "2":
            update_entry()
        elif choice == "3":
            deprecate_entry()
        elif choice == "4":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1-4.")


if __name__ == "__main__":
    main()
