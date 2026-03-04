from process_logging import log_news_process
import os

def test_logging():
    print("Testing logging function...")
    
    original_news = "Test news content: New factory opened in Khabarovsk."
    proposal = "Recommendation: Offer salary project."
    region = "Хабаровский край"
    recipients = [123456789, 987654321]
    
    log_news_process(original_news, proposal, region, recipients)
    
    if os.path.isfile("news_processing_log.csv"):
        print("Log file created successfully.")
        with open("news_processing_log.csv", "r", encoding="utf-8") as f:
            content = f.read()
            print("Log file content:")
            print(content)
    else:
        print("Error: Log file was not created.")

if __name__ == "__main__":
    test_logging()
