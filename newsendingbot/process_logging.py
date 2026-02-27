import csv
import os
from datetime import datetime
from typing import List, Optional

# File to store logs
LOG_FILE = "news_processing_log.csv"

def log_news_process(original_news: str, proposal: str, region: str, recipients: List[int]):
    """
    Logs the details of the news processing flow to a CSV file.

    Args:
        original_news (str): The original text of the news.
        proposal (str): The generated proposal text.
        region (str): The region associated with the news.
        recipients (List[int]): List of user IDs who received the proposal.
    """
    file_exists = os.path.isfile(LOG_FILE)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Prepare the row
    row = [
        timestamp,
        original_news,
        proposal,
        region,
        str(recipients)  # Convert list to string for CSV storage
    ]
    
    try:
        with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write header if file is new
            if not file_exists:
                writer.writerow(["Timestamp", "Original News", "Proposal", "Region", "Recipients"])
            
            writer.writerow(row)
            
    except Exception as e:
        # Fallback to standard print if logging fails, or use standard logging if configured elsewhere
        print(f"Error writing to log file: {e}")
