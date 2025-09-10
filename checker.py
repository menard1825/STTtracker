import os
import sys
import subprocess
import firebase_admin
from firebase_admin import credentials, firestore

def run_command(command):
    """Runs a command and returns its stdout, printing stderr."""
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.stderr:
        print(f"STDERR from '{' '.join(command)}':\n{result.stderr}", file=sys.stderr)
    if result.returncode != 0:
        print(f"Command '{' '.join(command)}' failed with exit code {result.returncode}", file=sys.stderr)
        return None
    return result.stdout.strip()

def main():
    """
    Main orchestrator script.
    """
    print("--- Starting Southwest Price Check ---")
    
    # --- Firebase Initialization ---
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Successfully connected to Firestore.")
    except Exception as e:
        print(f"FATAL: Could not initialize Firebase Admin SDK: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Fetch all tracked flights from all users ---
    # NOTE: You MUST replace 'default-app-id' with your actual App ID if it's different.
    # You can find your App ID in the global __app_id variable in your index.html.
    app_id = "default-app-id" 
    users_ref = db.collection('artifacts', app_id, 'users').stream()

    flight_count = 0
    for user in users_ref:
        print(f"\nProcessing flights for user: {user.id}")
        flights_ref = user.reference.collection('flights').stream()
        
        for flight in flights_ref:
            flight_count += 1
            flight_data = flight.to_dict()
            doc_id = flight.id
            
            print(f"  Checking flight: {flight_data['from']} -> {flight_data['to']} on {flight_data['depart']}")

            # --- 1. Run the Scraper ---
            scraper_command = [
                sys.executable, "save_results_via_deeplink.py",
                "--trip-type", flight_data.get("tripType", "oneway"),
                "--origin", flight_data.get("from"),
                "--destination", flight_data.get("to"),
                "--depart-date", flight_data.get("depart"),
            ]
            if flight_data.get("tripType") == "roundtrip":
                scraper_command.extend(["--return-date", flight_data.get("returnDate")])
            
            run_command(scraper_command)

            # --- 2. Run the Parser ---
            parser_command = [sys.executable, "parse_results.py"]
            current_price_str = run_command(parser_command)

            if not current_price_str or current_price_str in ["NOT_FOUND", "NO_FLIGHTS"]:
                print(f"    Could not find a price. Status: {current_price_str}. Skipping update.")
                continue
            
            try:
                current_price = float(current_price_str)
                # Assuming 'paid' is a string like "145.98" or "145.98 or 8500 pts"
                paid_price_str = flight_data.get("paid", "0").split(" ")[0]
                paid_price = float(paid_price_str)
            except (ValueError, TypeError) as e:
                print(f"    Error converting prices to numbers (current: '{current_price_str}', paid: '{flight_data.get('paid')}'). Skipping. Error: {e}")
                continue

            # --- 3. Compare prices and update DB ---
            new_status = "monitoring"
            if current_price < paid_price:
                new_status = "dropped"
                print(f"    PRICE DROPPED! You paid ${paid_price}, current is ${current_price}")
            elif current_price > paid_price:
                new_status = "higher"
                print(f"    Price is higher/same. You paid ${paid_price}, current is ${current_price}")
            
            update_data = {
                "current": f"${current_price:.2f}",
                "status": new_status,
            }

            try:
                flight.reference.update(update_data)
                print(f"    Successfully updated Firestore for flight {doc_id}.")
            except Exception as e:
                print(f"    ERROR updating Firestore for flight {doc_id}: {e}", file=sys.stderr)
    
    if flight_count == 0:
        print("No flights found in the database to check.")

    print("\n--- Price Check Complete ---")

if __name__ == "__main__":
    main()
