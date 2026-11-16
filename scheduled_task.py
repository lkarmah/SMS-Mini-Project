from datetime import datetime, timezone

def main():
    print("SMS Mini Project scheduled task started")

    current_time = datetime.now(timezone.utc)

    print(f"Execution time: {current_time}")
    print("Scheduled task completed successfully")


if __name__ == "__main__":
    main()