import os
import json
import boto3
import requests
import csv
import io
import datetime

# --- Retrieve API Credentials from Secrets Manager ---
SECRET_NAME = os.environ.get("KROGER_API_SECRET", "my/kroger/api/keys")

def get_api_credentials():
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager")
    try:
        response = client.get_secret_value(SecretId=SECRET_NAME)
        secret = json.loads(response["SecretString"])
        return secret["CLIENT_ID"], secret["CLIENT_SECRET"]
    except Exception as e:
        print("Error retrieving secret:", e)
        raise e

# Retrieve the API credentials from Secrets Manager
CLIENT_ID, CLIENT_SECRET = get_api_credentials()

# --- API Endpoints and Configuration ---
TOKEN_URL = "https://api.kroger.com/v1/connect/oauth2/token"
LOCATIONS_URL = "https://api.kroger.com/v1/locations"
PRODUCTS_URL = "https://api.kroger.com/v1/products"

# Read custom UPC from environment variable; if provided, use it.
CUSTOM_UPC = os.environ.get("CUSTOM_UPC", "").strip()

if CUSTOM_UPC:
    UPC_CODES = [CUSTOM_UPC]
else:
    UPC_CODES = [
        "0001111060903",  # Basic Eggs
        "0001111061748",  # Organic Eggs
        "0001111002449",  # Cage-Free Eggs
        "0001111061830"   # Other Large Eggs
    ]

# Target cities with representative ZIP codes
CITIES = {
    "Nashville, TN": "*****",
    "Knoxville, TN": "*****",
    "Atlanta, GA": "*****",
    "Louisville, KY": "*****",
    "Cincinnati, OH": "*****",
    "Myrtle Beach, SC": "*****"
}

# Persistent storage keys and S3 bucket name (set via environment variable)
S3_BUCKET = os.environ.get("S3_BUCKET", "eggciting")
CSV_KEY = "egg_prices.csv"
HTML_KEY = "index.html"

# --- Helper Functions ---

def get_auth_token():
    data = {"grant_type": "client_credentials", "scope": "product.compact"}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(TOKEN_URL, headers=headers, data=data, auth=(CLIENT_ID, CLIENT_SECRET))
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        raise Exception(f"Failed to get token: {response.status_code} {response.text}")

def get_locations(auth_token, zip_code, city_name, radius=15, limit=20):
    headers = {"Accept": "application/json", "Authorization": f"Bearer {auth_token}"}
    params = {
        "filter.zipCode.near": zip_code,
        "filter.radiusInMiles": radius,
        "filter.limit": limit
    }
    response = requests.get(LOCATIONS_URL, headers=headers, params=params)
    if response.status_code == 200:
        locations = response.json().get("data", [])
        # Return tuple: (city, location_id, store name, store city)
        return [(city_name, loc["locationId"], loc.get("name", "Unknown Store"),
                 loc.get("address", {}).get("city", "Unknown"))
                for loc in locations]
    else:
        print(f"Failed to fetch locations for {city_name}: {response.status_code} {response.text}")
        return []

def get_product_price(auth_token, location_id):
    headers = {"Accept": "application/json", "Authorization": f"Bearer {auth_token}"}
    for upc in UPC_CODES:
        params = {"filter.term": upc, "filter.locationId": location_id}
        response = requests.get(PRODUCTS_URL, headers=headers, params=params)
        if response.status_code == 200:
            products = response.json().get("data", [])
            if products:
                product = products[0]  # Assume first result is relevant
                if "items" in product and product["items"]:
                    first_item = product["items"][0]
                    if "price" in first_item and "regular" in first_item["price"]:
                        return first_item["price"]["regular"], upc
        else:
            print(f"Error for location {location_id}, UPC {upc}: {response.status_code} {response.text}")
    return None, None  # No price found

def download_csv_from_s3():
    s3 = boto3.client("s3")
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=CSV_KEY)
        csv_content = response['Body'].read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(csv_content))
        return list(reader)
    except s3.exceptions.NoSuchKey:
        return []
    except Exception as e:
        print("Error downloading CSV:", e)
        return []

def save_csv_to_s3(data):
    fieldnames = ["city", "location_id", "store", "upc", "price", "date"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)
    csv_data = output.getvalue()
    s3 = boto3.client("s3")
    s3.put_object(Bucket=S3_BUCKET, Key=CSV_KEY, Body=csv_data)

def generate_html_report(csv_data):
    html_lines = []
    html_lines.append("""
<!DOCTYPE html>
<html>
<head>
    <title>Egg Price Report</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1, h2 {
            text-align: center;
            color: #333;
        }
        h1 {
            margin-bottom: 10px;
        }
        h2 {
            margin-bottom: 40px;
        }
        h2 a {
            color: #2c3e50;
            text-decoration: none;
        }
        h2 a:hover {
            text-decoration: underline;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 40px;
        }
        .city-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .city-card h2 {
            color: #2c3e50;
            margin-top: 0;
            margin-bottom: 15px;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
            text-align: left;
        }
        .city-card p {
            color: #555;
            line-height: 1.5;
            margin: 10px 0;
        }
        .price {
            font-size: 1.2em;
            color: #27ae60;
            font-weight: bold;
        }
        .price-change {
            font-size: 0.9em;
            color: #666;
        }
        .about-section {
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .about-section h3 {
            color: #2c3e50;
            margin-bottom: 15px;
        }
        .about-section p {
            color: #666;
            max-width: 800px;
            margin: 15px auto;
            line-height: 1.6;
        }
        .about-section a {
            color: #27ae60;
            text-decoration: none;
        }
        .about-section a:hover {
            text-decoration: underline;
        }
        .no-data {
            color: #e74c3c;
            font-style: italic;
        }
        @media (max-width: 900px) {
            .grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        @media (max-width: 600px) {
            .grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Egg Price Report</h1>
        <h2><a href="https://www.christofferturpin.com/publicFiles/resume.pdf">By Chris Turpin</a></h2>
        <div class="grid">
""")
    
    # Generate city cards
    for city in CITIES.keys():
        html_lines.append('<div class="city-card">')
        html_lines.append(f"<h2>{city}</h2>")
        
        # Filter rows for this city where price exists
        city_rows = [row for row in csv_data if row["city"] == city and row["price"] not in ("", None)]
        
        # Parse date/price with fallback
        for row in city_rows:
            try:
                row["price"] = float(row["price"])
            except:
                row["price"] = None
            
            parsed_date = None
            if row["date"]:
                try:
                    parsed_date = datetime.datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        parsed_date = datetime.datetime.strptime(row["date"], "%m/%d/%Y %H:%M")
                    except ValueError:
                        parsed_date = None
            row["date_dt"] = parsed_date
        
        # Keep only rows with valid price and date
        city_rows = [row for row in city_rows if row["price"] is not None and row["date_dt"] is not None]
        
        if city_rows:
            city_rows.sort(key=lambda r: r["date_dt"], reverse=True)
            latest = city_rows[0]
            current_price = latest["price"]
            current_date = latest["date"]
            html_lines.append(f'<p class="price">Current Price: ${current_price:.2f}</p>')
            html_lines.append(f'<p>as of {current_date}</p>')
            
            try:
                dt_current = latest["date_dt"]
                seven_days_ago = dt_current - datetime.timedelta(days=7)
                older_rows = [row for row in city_rows if seven_days_ago <= row["date_dt"] < dt_current]
                
                if older_rows:
                    avg_price = sum(r["price"] for r in older_rows) / len(older_rows)
                    price_change = current_price - avg_price
                    sign = "+" if price_change >= 0 else ""
                    html_lines.append(
                        f'<p class="price-change">7-day change: {sign}${abs(price_change):.2f}<br>'
                        f'(7-day avg: ${avg_price:.2f})</p>'
                    )
                else:
                    html_lines.append('<p class="price-change">Insufficient data for price trend</p>')
            except Exception as e:
                html_lines.append('<p class="price-change">Error computing price trend</p>')
        else:
            html_lines.append('<p class="no-data">No data available</p>')
        
        html_lines.append("</div>")  # Close city-card

    html_lines.append("""
        </div>
        <div class="about-section">
            <h3>About This Project</h3>
            <p>Explore another serverless AWS project by <a href="https://www.christofferturpin.com/publicFiles/resume.pdf">Chris Turpin</a>, highlighting Infrastructure as Code (IaC) in action. An AWS Lambda function fetches data from the Kroger API to dynamically generate the HTML content you're viewing right now. AWS Secrets Manager securely handles all credentials, making deployment seamless with the provided SAM template available <a href="https://www.github.com/christofferturpin">here</a>.</p>
            <p>Curious about the build process and challenges along the way? Dive deeper into the project's development by checking out the GitHub devlog linked above for behind-the-scenes insights.</p>
        </div>
    </div>
</body>
</html>
""")

    return "\n".join(html_lines)
    

def upload_html_report(html_content):
    s3 = boto3.client("s3")
    s3.put_object(Bucket=S3_BUCKET, Key=HTML_KEY, Body=html_content, ContentType="text/html")

# --- Main Lambda Handler ---
def lambda_handler(event, context):
    try:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_rows = []
        token = get_auth_token()
        # For each target city, query for an egg price
        for city, zip_code in CITIES.items():
            locations = get_locations(token, zip_code, city)
            price_found = False
            for city_label, location_id, store, store_city in locations:
                price, upc_used = get_product_price(token, location_id)
                if price is not None:
                    print(f"{city_label} - {store} (ID: {location_id}) - UPC: {upc_used} - ${price}")
                    new_rows.append({
                        "city": city_label,
                        "location_id": location_id,
                        "store": store,
                        "upc": upc_used,
                        "price": price,
                        "date": now_str
                    })
                    price_found = True
                    break
            if not price_found:
                print(f"{city} - No available egg price")
                new_rows.append({
                    "city": city,
                    "location_id": "N/A",
                    "store": "N/A",
                    "upc": "N/A",
                    "price": "",
                    "date": now_str
                })
        # Download existing CSV (if exists) and append new data
        existing_rows = download_csv_from_s3()
        all_rows = existing_rows + new_rows
        # Save the updated CSV back to S3
        save_csv_to_s3(all_rows)
        # Generate the HTML report from the entire CSV data
        html_report = generate_html_report(all_rows)
        # Upload the HTML report as "index.html" (overwriting previous version)
        upload_html_report(html_report)
        message = "Egg prices updated. CSV and index.html uploaded to S3."
        print(message)
        return {"statusCode": 200, "body": message}
    except Exception as e:
        print("Error:", e)
        return {"statusCode": 500, "body": str(e)}
